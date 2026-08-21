"""Safe local artifact storage adapter from ADR-004."""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import stat
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from video_app.domain.models import BackendOutput, GenerationResult

_KEY_PATTERN = re.compile(r"^[0-9a-f]{32}\.mp4$")


def _is_link(path: Path) -> bool:
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return path.is_symlink() or bool(
        attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


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

    def _path_for(self, storage_key: str) -> Path:
        if not _KEY_PATTERN.fullmatch(storage_key):
            raise ValueError("invalid storage key")
        root = self.root.resolve(strict=True)
        path = root / storage_key
        if path.parent != root:
            raise ValueError("storage key escaped artifact root")
        return path

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

    async def discard_candidate(self, output: BackendOutput) -> None:
        await asyncio.to_thread(output.temporary_path.unlink, missing_ok=True)

    async def delete(self, storage_key: str) -> None:
        path = self._path_for(storage_key)
        if path.exists() and _is_link(path):
            raise ValueError("stored artifact must not be a link or reparse point")
        await asyncio.to_thread(path.unlink, missing_ok=True)

    def resolve_for_read(self, storage_key: str) -> Path:
        path = self._path_for(storage_key)
        if not path.is_file() or _is_link(path):
            raise FileNotFoundError(storage_key)
        return path

