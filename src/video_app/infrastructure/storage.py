"""Safe local artifact storage adapter from ADR-004."""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import stat
from collections.abc import AsyncIterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from video_app.application.assets import AssetTooLargeError, InvalidAssetError, StoredUpload
from video_app.domain.models import BackendOutput, GenerationResult

_KEY_PATTERN = re.compile(r"^(?:[0-9a-f]{32}\.mp4|uploads/[0-9a-f]{32}\.(?:png|jpg|wav|mp4))$")
_UPLOAD_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "audio/wav": ".wav",
    "video/mp4": ".mp4",
}


def _matches_magic(media_type: str, header: bytes) -> bool:
    if media_type == "image/png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    if media_type == "image/jpeg":
        return header.startswith(b"\xff\xd8\xff")
    if media_type == "audio/wav":
        return len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WAVE"
    if media_type == "video/mp4":
        return len(header) >= 12 and header[4:8] == b"ftyp"
    return False


def _is_link(path: Path) -> bool:
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return path.is_symlink() or bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _validate_candidate(path: Path) -> None:
    if not path.is_absolute() or not path.exists() or not path.is_file():
        raise ValueError("artifact candidate must be an existing absolute file")
    if _is_link(path):
        raise ValueError("artifact candidate must not be a link or reparse point")
    if path.suffix.lower() != ".mp4":
        raise ValueError("artifact candidate must use the .mp4 extension")
    with path.open("rb") as source:
        header = source.read(12)
    if len(header) < 12 or header[4:8] != b"ftyp":
        raise ValueError("artifact candidate is not an MP4 container")


def _validate_png_candidate(path: Path) -> None:
    if not path.is_absolute() or not path.exists() or not path.is_file():
        raise ValueError("image candidate must be an existing absolute file")
    if _is_link(path):
        raise ValueError("image candidate must not be a link or reparse point")
    if path.suffix.lower() != ".png":
        raise ValueError("image candidate must use the .png extension")
    with path.open("rb") as source:
        header = source.read(8)
    if header != b"\x89PNG\r\n\x1a\n":
        raise ValueError("image candidate is not a PNG")


def _copy_atomic(source_path: Path, partial_path: Path, final_path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    try:
        with source_path.open("rb") as source, partial_path.open("xb") as destination:
            while chunk := source.read(1024 * 1024):
                destination.write(chunk)
                digest.update(chunk)
                size += len(chunk)
            destination.flush()
            os.fsync(destination.fileno())
        if size <= 0:
            raise ValueError("artifact candidate must not be empty")
        os.replace(partial_path, final_path)
        source_path.unlink()
        return size, digest.hexdigest()
    except BaseException:
        partial_path.unlink(missing_ok=True)
        final_path.unlink(missing_ok=True)
        raise


@dataclass(frozen=True, slots=True)
class LocalArtifactStore:
    root: Path

    def __post_init__(self) -> None:
        if not self.root.is_absolute() or not self.root.exists() or not self.root.is_dir():
            raise ValueError("artifact root must be an existing absolute directory")
        if _is_link(self.root):
            raise ValueError("artifact root must not be a link or reparse point")
        upload_root = self.root / "uploads"
        upload_root.mkdir(exist_ok=True)
        if _is_link(upload_root):
            raise ValueError("upload root must not be a link or reparse point")

    def _path_for(self, storage_key: str) -> Path:
        if not _KEY_PATTERN.fullmatch(storage_key):
            raise ValueError("invalid storage key")
        root = self.root.resolve(strict=True)
        path = root / storage_key
        if path.parent not in {root, root / "uploads"}:
            raise ValueError("storage key escaped artifact root")
        return path

    async def store_upload(
        self,
        *,
        filename: str,
        declared_media_type: str,
        chunks: AsyncIterable[bytes],
        max_bytes: int,
    ) -> StoredUpload:
        clean_name = Path(filename).name
        if clean_name != filename or not clean_name or len(clean_name) > 255:
            raise InvalidAssetError("invalid upload filename")
        extension = _UPLOAD_TYPES.get(declared_media_type)
        if extension is None or Path(clean_name).suffix.lower() not in {
            extension,
            ".jpeg" if extension == ".jpg" else extension,
        }:
            raise InvalidAssetError("upload media type or extension is not allowed")
        key = f"uploads/{uuid4().hex}{extension}"
        final_path = self._path_for(key)
        if _is_link(final_path.parent):
            raise InvalidAssetError("upload storage directory is not safe")
        partial_path = final_path.with_suffix(".part")
        digest = hashlib.sha256()
        size = 0
        header = bytearray()
        try:
            with partial_path.open("xb") as destination:
                async for chunk in chunks:
                    if not chunk:
                        continue
                    size += len(chunk)
                    if size > max_bytes:
                        raise AssetTooLargeError("upload exceeds configured size limit")
                    if len(header) < 16:
                        header.extend(chunk[: 16 - len(header)])
                    destination.write(chunk)
                    digest.update(chunk)
                destination.flush()
                os.fsync(destination.fileno())
            if size == 0 or not _matches_magic(declared_media_type, bytes(header)):
                raise InvalidAssetError("upload content does not match its media type")
            os.replace(partial_path, final_path)
        except BaseException:
            partial_path.unlink(missing_ok=True)
            final_path.unlink(missing_ok=True)
            raise
        return StoredUpload(key, clean_name, declared_media_type, size, digest.hexdigest())

    async def store(
        self,
        job_id: str,
        output: BackendOutput,
        created_at: datetime,
    ) -> GenerationResult:
        if not job_id or job_id.isspace():
            raise ValueError("job_id must not be empty")
        await asyncio.to_thread(_validate_candidate, output.temporary_path)
        key = f"{uuid4().hex}.mp4"
        final_path = self._path_for(key)
        partial_path = final_path.with_suffix(".part")
        size, checksum = await asyncio.to_thread(
            _copy_atomic,
            output.temporary_path,
            partial_path,
            final_path,
        )
        return GenerationResult(
            storage_key=key,
            media_type="video/mp4",
            resolution=output.resolution,
            frame_count=output.frame_count,
            duration_seconds=output.duration_seconds,
            size_bytes=size,
            sha256=checksum,
            created_at=created_at,
        )

    async def store_generated_image(self, *, filename: str, candidate_path: Path) -> StoredUpload:
        clean_name = Path(filename).name
        if (
            clean_name != filename
            or not clean_name
            or len(clean_name) > 255
            or Path(clean_name).suffix.lower() != ".png"
        ):
            raise InvalidAssetError("generated image filename must be a safe PNG name")
        await asyncio.to_thread(_validate_png_candidate, candidate_path)
        key = f"uploads/{uuid4().hex}.png"
        final_path = self._path_for(key)
        partial_path = final_path.with_suffix(".part")
        try:
            size, checksum = await asyncio.to_thread(
                _copy_atomic,
                candidate_path,
                partial_path,
                final_path,
            )
        except BaseException:
            await asyncio.to_thread(candidate_path.unlink, missing_ok=True)
            raise
        return StoredUpload(key, clean_name, "image/png", size, checksum)

    async def discard_candidate(self, output: BackendOutput) -> None:
        await asyncio.to_thread(output.temporary_path.unlink, missing_ok=True)

    async def delete(self, storage_key: str) -> None:
        path = self._path_for(storage_key)
        if _is_link(path.parent):
            raise ValueError("stored artifact parent must not be a link or reparse point")
        if path.exists() and _is_link(path):
            raise ValueError("stored artifact must not be a link or reparse point")
        await asyncio.to_thread(path.unlink, missing_ok=True)

    def resolve_for_read(self, storage_key: str) -> Path:
        path = self._path_for(storage_key)
        if _is_link(path.parent):
            raise FileNotFoundError(storage_key)
        if not path.is_file() or _is_link(path):
            raise FileNotFoundError(storage_key)
        return path
