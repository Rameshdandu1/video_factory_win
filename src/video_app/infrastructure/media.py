"""Pinned and bounded ffprobe media inspection adapter."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Mapping
from fractions import Fraction
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from PIL import Image, ImageChops, ImageOps, UnidentifiedImageError

from video_app.application.assets import MediaInspectionError
from video_app.application.library import StartingFrameRenderer, StartingFrameRenderError
from video_app.domain.assets import MediaMetadata
from video_app.domain.library import (
    CompositionAssetSnapshot,
    CompositionFit,
    StartingFrameComposition,
    StartingFrameLayer,
)


def _fraction(value: object, field: str) -> Fraction:
    if not isinstance(value, str):
        raise MediaInspectionError(f"ffprobe {field} is missing")
    try:
        parsed = Fraction(value)
    except (ValueError, ZeroDivisionError) as error:
        raise MediaInspectionError(f"ffprobe {field} is invalid") from error
    if parsed <= 0:
        raise MediaInspectionError(f"ffprobe {field} must be positive")
    return parsed


def _positive_int(value: object, field: str) -> int:
    try:
        parsed = int(cast(str | int, value))
    except (TypeError, ValueError) as error:
        raise MediaInspectionError(f"ffprobe {field} is invalid") from error
    if parsed <= 0:
        raise MediaInspectionError(f"ffprobe {field} must be positive")
    return parsed


def parse_ffprobe(payload: bytes) -> MediaMetadata:
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MediaInspectionError("ffprobe returned invalid JSON") from error
    if not isinstance(document, dict) or not isinstance(document.get("streams"), list):
        raise MediaInspectionError("ffprobe response is missing streams")
    format_data = document.get("format")
    if not isinstance(format_data, dict):
        raise MediaInspectionError("ffprobe response is missing format metadata")
    format_name = format_data.get("format_name")
    if not isinstance(format_name, str) or not format_name:
        raise MediaInspectionError("ffprobe format name is missing")
    duration = _fraction(format_data.get("duration"), "duration")
    duration_ms = max(1, round(duration * 1000))
    video: dict[str, Any] | None = None
    audio: dict[str, Any] | None = None
    for raw_stream in document["streams"]:
        if not isinstance(raw_stream, dict):
            continue
        if raw_stream.get("codec_type") == "video" and video is None:
            video = raw_stream
        elif raw_stream.get("codec_type") == "audio" and audio is None:
            audio = raw_stream
    width = height = frame_num = frame_den = None
    if video is not None:
        width = _positive_int(video.get("width"), "video width")
        height = _positive_int(video.get("height"), "video height")
        frame_rate = _fraction(video.get("avg_frame_rate"), "average frame rate")
        frame_num, frame_den = frame_rate.numerator, frame_rate.denominator
    sample_rate = channels = sample_count = None
    if audio is not None:
        sample_rate = _positive_int(audio.get("sample_rate"), "audio sample rate")
        channels = _positive_int(audio.get("channels"), "audio channels")
        sample_count = max(1, round(duration * sample_rate))
    return MediaMetadata(
        format_name=format_name,
        duration_ms=duration_ms,
        width=width,
        height=height,
        frame_rate_numerator=frame_num,
        frame_rate_denominator=frame_den,
        sample_rate=sample_rate,
        channels=channels,
        sample_count=sample_count,
    )


async def _read_bounded(stream: asyncio.StreamReader, limit: int) -> bytes:
    result = bytearray()
    while chunk := await stream.read(min(65_536, limit + 1 - len(result))):
        result.extend(chunk)
        if len(result) > limit:
            raise MediaInspectionError("ffprobe output exceeded the configured limit")
    return bytes(result)


class FfprobeMediaInspector:
    def __init__(
        self,
        *,
        executable: Path,
        expected_sha256: str,
        expected_version_line: str,
        timeout_seconds: float,
        max_output_bytes: int,
    ) -> None:
        self._executable = executable
        self._expected_sha256 = expected_sha256
        self._expected_version_line = expected_version_line
        self._timeout_seconds = timeout_seconds
        self._max_output_bytes = max_output_bytes

    @property
    def revision(self) -> str:
        return f"{self._expected_version_line} sha256:{self._expected_sha256}"

    async def _run(self, *arguments: str) -> tuple[bytes, bytes]:
        process = await asyncio.create_subprocess_exec(
            str(self._executable),
            *arguments,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert process.stdout is not None and process.stderr is not None
        try:
            stdout, stderr, return_code = await asyncio.wait_for(
                asyncio.gather(
                    _read_bounded(process.stdout, self._max_output_bytes),
                    _read_bounded(process.stderr, self._max_output_bytes),
                    process.wait(),
                ),
                timeout=self._timeout_seconds,
            )
        except asyncio.TimeoutError as error:
            process.kill()
            await process.wait()
            raise MediaInspectionError("ffprobe inspection timed out") from error
        except BaseException:
            process.kill()
            await process.wait()
            raise
        if return_code != 0:
            raise MediaInspectionError("ffprobe could not inspect the media")
        return stdout, stderr

    async def _verify(self) -> None:
        digest = await asyncio.to_thread(_sha256_file, self._executable)
        if digest != self._expected_sha256:
            raise MediaInspectionError("ffprobe executable checksum does not match its pin")
        stdout, _ = await self._run("-version")
        first_line = stdout.decode("utf-8", errors="replace").splitlines()[0:1]
        if first_line != [self._expected_version_line]:
            raise MediaInspectionError("ffprobe version does not match its pin")

    async def inspect(self, path: Path) -> MediaMetadata:
        if not path.is_absolute() or not path.is_file():
            raise MediaInspectionError("asset is unavailable for inspection")
        await self._verify()
        stdout, _ = await self._run(
            "-v",
            "error",
            "-protocol_whitelist",
            "file",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            str(path),
        )
        return parse_ffprobe(stdout)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _open_rgba(path: Path) -> Image.Image:
    try:
        with Image.open(path) as source:
            if source.format not in {"PNG", "JPEG"}:
                raise StartingFrameRenderError("composition sources must be PNG or JPEG")
            if source.width < 1 or source.height < 1:
                raise StartingFrameRenderError("composition source dimensions must be positive")
            if (
                source.width > 8192
                or source.height > 8192
                or source.width * source.height > 33_554_432
            ):
                raise StartingFrameRenderError("composition source exceeds the safe image limit")
            source.load()
            return cast(Image.Image, source.convert("RGBA"))
    except (OSError, UnidentifiedImageError) as error:
        raise StartingFrameRenderError("composition source could not be decoded") from error


def _verify_source(snapshot: CompositionAssetSnapshot, source_paths: Mapping[str, Path]) -> Path:
    path = source_paths.get(snapshot.asset_id)
    if path is None:
        raise StartingFrameRenderError("a pinned composition source is missing")
    if _file_sha256(path) != snapshot.asset_sha256:
        raise StartingFrameRenderError("a composition source checksum does not match its pin")
    return path


def _crop(image: Image.Image, layer: StartingFrameLayer) -> Image.Image:
    crop = layer.transform.crop
    if crop is None:
        return image
    if crop.x + crop.width > image.width or crop.y + crop.height > image.height:
        raise StartingFrameRenderError("source crop is outside the decoded image")
    return image.crop((crop.x, crop.y, crop.x + crop.width, crop.y + crop.height))


def _fit(image: Image.Image, layer: StartingFrameLayer) -> Image.Image:
    size = (layer.transform.width, layer.transform.height)
    if layer.transform.fit is CompositionFit.STRETCH:
        return image.resize(size, Image.Resampling.LANCZOS)
    if layer.transform.fit is CompositionFit.COVER:
        return ImageOps.fit(image, size, Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    contained = ImageOps.contain(image, size, Image.Resampling.LANCZOS)
    result = Image.new("RGBA", size, (0, 0, 0, 0))
    result.alpha_composite(
        contained,
        ((size[0] - contained.width) // 2, (size[1] - contained.height) // 2),
    )
    return result


def _apply_mask_and_opacity(
    image: Image.Image,
    layer: StartingFrameLayer,
    source_paths: Mapping[str, Path],
    source_size: tuple[int, int],
) -> Image.Image:
    alpha = image.getchannel("A")
    if layer.mask is not None:
        mask = _open_rgba(_verify_source(layer.mask, source_paths))
        if mask.size != source_size:
            raise StartingFrameRenderError("manual mask dimensions must match the source image")
        mask = _fit(_crop(mask, layer), layer)
        mask_luminance = ImageOps.grayscale(mask)
        mask_strength = ImageChops.multiply(mask_luminance, mask.getchannel("A"))
        alpha = ImageChops.multiply(alpha, mask_strength)
    if layer.transform.opacity_basis_points != 10_000:
        basis_points = layer.transform.opacity_basis_points
        alpha = alpha.point([(value * basis_points + 5_000) // 10_000 for value in range(256)])
    result = image.copy()
    result.putalpha(alpha)
    return result


def _render_composition(
    composition: StartingFrameComposition,
    source_paths: Mapping[str, Path],
    output_path: Path,
) -> None:
    rgba = composition.background_rgba[1:]
    background = tuple(int(rgba[index : index + 2], 16) for index in range(0, 8, 2))
    canvas = Image.new("RGBA", (composition.canvas_width, composition.canvas_height), background)
    try:
        for layer in composition.layers:
            source = _open_rgba(_verify_source(layer.source, source_paths))
            source_size = source.size
            raster = _fit(_crop(source, layer), layer)
            raster = _apply_mask_and_opacity(
                raster,
                layer,
                source_paths,
                source_size,
            )
            if layer.transform.rotation_millidegrees:
                raster = raster.rotate(
                    layer.transform.rotation_millidegrees / 1000,
                    resample=Image.Resampling.BICUBIC,
                    expand=True,
                )
            x = layer.transform.x - (raster.width - layer.transform.width) // 2
            y = layer.transform.y - (raster.height - layer.transform.height) // 2
            canvas.alpha_composite(raster, (x, y))
        canvas.save(output_path, format="PNG", compress_level=9, optimize=False)
    except BaseException:
        output_path.unlink(missing_ok=True)
        raise


class PillowStartingFrameRenderer(StartingFrameRenderer):
    """Deterministic RGBA rasterizer for Starting-frame Composition Contract v1."""

    def __init__(self, output_root: Path) -> None:
        if not output_root.is_absolute() or not output_root.exists() or not output_root.is_dir():
            raise ValueError("composition temporary root must be an existing absolute directory")
        self._output_root = output_root

    @property
    def revision(self) -> str:
        return "pillow-11.3.0/composition-v1"

    async def render(
        self,
        composition: StartingFrameComposition,
        source_paths: Mapping[str, Path],
    ) -> Path:
        output_path = self._output_root / f"composition_{uuid4().hex}.png"
        await asyncio.to_thread(_render_composition, composition, source_paths, output_path)
        return output_path

    async def discard_candidate(self, candidate_path: Path) -> None:
        root = self._output_root.resolve(strict=True)
        try:
            candidate = candidate_path.resolve(strict=False)
        except OSError as error:
            raise ValueError("composition candidate path could not be resolved") from error
        if candidate.parent != root or not candidate.name.startswith("composition_"):
            raise ValueError("composition candidate is outside the renderer temporary root")
        await asyncio.to_thread(candidate.unlink, missing_ok=True)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
