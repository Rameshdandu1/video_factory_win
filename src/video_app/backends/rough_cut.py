"""Pinned FFmpeg rough-cut adapter for approved storyboard and dialogue manifests."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import signal
import stat
import subprocess
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from video_app.domain.models import (
    BackendOutput,
    ErrorCode,
    GenerationMode,
    GenerationRequest,
    ModelCapability,
    Progress,
    Resolution,
    RoughCutManifest,
    RoughCutSource,
)
from video_app.domain.ports import BackendCancelledError, BackendFailureError, GenerationContext

ROUGH_CUT_BACKEND_NAME = "ffmpeg-rough-cut"
ROUGH_CUT_BACKEND_REVISION = "ffmpeg-rough-cut-v1"


class RoughCutConfigurationError(ValueError):
    """Raised when a media runtime differs from its reviewed pins."""


def _is_link(path: Path) -> bool:
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return path.is_symlink() or bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _regular_file(path: Path, field: str) -> Path:
    if not path.is_absolute() or not path.is_file() or _is_link(path):
        raise RoughCutConfigurationError(f"{field} must be an existing absolute regular file")
    return path.resolve(strict=True)


def _regular_directory(path: Path, field: str) -> Path:
    if not path.is_absolute() or not path.is_dir() or _is_link(path):
        raise RoughCutConfigurationError(f"{field} must be an existing absolute regular directory")
    return path.resolve(strict=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _verify_executable(path: Path, sha256: str, version_line: str, name: str) -> Path:
    executable = _regular_file(path, name)
    if len(sha256) != 64 or any(character not in "0123456789abcdef" for character in sha256):
        raise RoughCutConfigurationError(f"{name} checksum must be lowercase SHA-256")
    if _sha256(executable) != sha256:
        raise RoughCutConfigurationError(f"{name} executable does not match qualification")
    try:
        measured = subprocess.run(
            [str(executable), "-version"],
            check=True,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            text=True,
            timeout=5,
        ).stdout.splitlines()[0]
    except (OSError, subprocess.SubprocessError, IndexError) as error:
        raise RoughCutConfigurationError(f"{name} version could not be verified") from error
    if measured != version_line:
        raise RoughCutConfigurationError(f"{name} version does not match qualification")
    return executable


@dataclass(frozen=True, slots=True)
class RoughCutRuntime:
    ffmpeg_executable: Path
    ffmpeg_sha256: str
    ffmpeg_version_line: str
    ffprobe_executable: Path
    ffprobe_sha256: str
    ffprobe_version_line: str
    output_root: Path
    resolution: Resolution
    fps_numerator: int
    fps_denominator: int
    frame_count: int
    deadline_seconds: int
    cancellation_poll_seconds: float = 0.25
    termination_grace_seconds: float = 5.0

    def __post_init__(self) -> None:
        ffmpeg = _verify_executable(
            self.ffmpeg_executable,
            self.ffmpeg_sha256,
            self.ffmpeg_version_line,
            "FFmpeg",
        )
        ffprobe = _verify_executable(
            self.ffprobe_executable,
            self.ffprobe_sha256,
            self.ffprobe_version_line,
            "ffprobe",
        )
        output = _regular_directory(self.output_root, "rough-cut output root")
        if (
            min(
                self.fps_numerator,
                self.fps_denominator,
                self.frame_count,
                self.deadline_seconds,
            )
            <= 0
        ):
            raise RoughCutConfigurationError("rough-cut runtime limits must be positive")
        if self.cancellation_poll_seconds <= 0 or self.termination_grace_seconds <= 0:
            raise RoughCutConfigurationError("rough-cut process timing must be positive")
        object.__setattr__(self, "ffmpeg_executable", ffmpeg)
        object.__setattr__(self, "ffprobe_executable", ffprobe)
        object.__setattr__(self, "output_root", output)


@dataclass(frozen=True, slots=True)
class FfmpegRoughCutBackend:
    runtime: RoughCutRuntime

    @property
    def name(self) -> str:
        return ROUGH_CUT_BACKEND_NAME

    @property
    def revision(self) -> str:
        return ROUGH_CUT_BACKEND_REVISION

    def capabilities(self) -> tuple[ModelCapability, ...]:
        return (
            ModelCapability(
                model_id=self.name,
                display_name="Approved storyboard rough cut",
                modes=frozenset({GenerationMode.ROUGH_CUT}),
                resolutions=frozenset({self.runtime.resolution}),
                frame_counts=frozenset({self.runtime.frame_count}),
            ),
        )

    def _supports(self, request: GenerationRequest) -> bool:
        manifest = request.rough_cut
        return (
            request.mode is GenerationMode.ROUGH_CUT
            and request.model == self.name
            and manifest is not None
            and manifest.required_backend == self.name
            and manifest.required_backend_revision == self.revision
            and request.resolution == self.runtime.resolution
            and manifest.fps_numerator == self.runtime.fps_numerator
            and manifest.fps_denominator == self.runtime.fps_denominator
            and request.frame_count == self.runtime.frame_count
        )

    async def _stop(self, process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        pid = cast(int | None, getattr(process, "pid", None))
        kill_group = cast(Any, getattr(os, "killpg", None))
        with suppress(ProcessLookupError):
            if os.name != "nt" and pid is not None and kill_group is not None:
                kill_group(pid, signal.SIGTERM)
            else:
                process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=self.runtime.termination_grace_seconds)
            return
        except asyncio.TimeoutError:
            pass
        with suppress(ProcessLookupError):
            if os.name != "nt" and pid is not None and kill_group is not None:
                kill_group(pid, cast(int, getattr(signal, "SIGKILL", signal.SIGTERM)))
            else:
                process.kill()
        await process.wait()

    async def _run(
        self,
        command: tuple[str, ...],
        context: GenerationContext,
        deadline: float,
        *,
        cwd: Path,
    ) -> None:
        options: dict[str, Any] = (
            {"creationflags": int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))}
            if os.name == "nt"
            else {"start_new_session": True}
        )
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            cwd=str(cwd),
            **options,
        )
        wait = asyncio.create_task(process.wait())
        loop = asyncio.get_running_loop()
        try:
            while not wait.done():
                if await context.is_cancellation_requested():
                    raise BackendCancelledError()
                if loop.time() >= deadline:
                    raise BackendFailureError(ErrorCode.MEDIA_RENDER_FAILED, retryable=True)
                try:
                    await asyncio.wait_for(
                        asyncio.shield(wait), timeout=self.runtime.cancellation_poll_seconds
                    )
                except asyncio.TimeoutError:
                    continue
            if await wait != 0:
                raise BackendFailureError(ErrorCode.MEDIA_RENDER_FAILED, retryable=True)
        except BaseException:
            await self._stop(process)
            wait.cancel()
            await asyncio.gather(wait, return_exceptions=True)
            raise

    async def _resolve_source(self, source: RoughCutSource, context: GenerationContext) -> Path:
        if context.resolve_input is None:
            raise BackendFailureError(ErrorCode.MEDIA_RENDER_FAILED, retryable=False)
        try:
            path = _regular_file(await context.resolve_input(source.storage_key), "rough-cut input")
            measured = await asyncio.to_thread(_sha256, path)
        except (OSError, ValueError, RoughCutConfigurationError) as error:
            raise BackendFailureError(ErrorCode.MEDIA_RENDER_FAILED, retryable=False) from error
        if measured != source.sha256:
            raise BackendFailureError(ErrorCode.MEDIA_RENDER_FAILED, retryable=False)
        return path

    def _shot_command(
        self,
        image: Path,
        audio: Path,
        destination: Path,
        duration_ms: int,
    ) -> tuple[str, ...]:
        duration = f"{duration_ms / 1000:.3f}"
        fps = f"{self.runtime.fps_numerator}/{self.runtime.fps_denominator}"
        width = self.runtime.resolution.width
        height = self.runtime.resolution.height
        filters = (
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"setsar=1,fps={fps},format=yuv420p[v];"
            f"[1:a]aresample=48000,apad,atrim=0:{duration},asetpts=PTS-STARTPTS[a]"
        )
        return (
            str(self.runtime.ffmpeg_executable),
            "-nostdin",
            "-v",
            "error",
            "-loop",
            "1",
            "-framerate",
            fps,
            "-i",
            str(image),
            "-i",
            str(audio),
            "-filter_complex",
            filters,
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-t",
            duration,
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "pcm_s16le",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-threads",
            "1",
            "-map_metadata",
            "-1",
            "-f",
            "matroska",
            "-y",
            str(destination),
        )

    def _concat_command(
        self, concat_file: Path, destination: Path, total_duration_ms: int
    ) -> tuple[str, ...]:
        return (
            str(self.runtime.ffmpeg_executable),
            "-nostdin",
            "-v",
            "error",
            "-f",
            "concat",
            "-safe",
            "1",
            "-i",
            str(concat_file),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-t",
            f"{total_duration_ms / 1000:.3f}",
            "-map_metadata",
            "-1",
            "-movflags",
            "+faststart",
            "-y",
            str(destination),
        )

    async def _probe(self, output: Path, manifest: RoughCutManifest) -> None:
        command = (
            str(self.runtime.ffprobe_executable),
            "-v",
            "error",
            "-count_frames",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,nb_read_frames:format=duration",
            "-of",
            "json",
            str(output),
        )
        try:
            completed = await asyncio.to_thread(
                subprocess.run,
                command,
                check=True,
                capture_output=True,
                stdin=subprocess.DEVNULL,
                timeout=30,
            )
            if len(completed.stdout) > 256 * 1024:
                raise ValueError("ffprobe output is too large")
            payload = json.loads(completed.stdout)
            stream = payload["streams"][0]
            duration = float(payload["format"]["duration"])
            frame_count = int(stream["nb_read_frames"])
            if (
                int(stream["width"]) != manifest.width
                or int(stream["height"]) != manifest.height
                or frame_count != manifest.frame_count
                or abs(duration - manifest.total_duration_ms / 1000) > 0.05
            ):
                raise ValueError("rough-cut output metadata does not match the manifest")
        except (
            OSError,
            subprocess.SubprocessError,
            ValueError,
            KeyError,
            IndexError,
            TypeError,
        ) as error:
            raise BackendFailureError(ErrorCode.MEDIA_RENDER_FAILED, retryable=False) from error

    async def generate(
        self,
        request: GenerationRequest,
        context: GenerationContext,
    ) -> BackendOutput:
        if not self._supports(request):
            raise BackendFailureError(ErrorCode.UNSUPPORTED_PARAMETERS, retryable=False)
        manifest = request.rough_cut
        assert manifest is not None
        root = self.runtime.output_root.resolve(strict=True)
        run_root = root / f"rough-cut-{uuid4().hex}"
        run_root.mkdir()
        if run_root.parent != root or _is_link(run_root):
            raise BackendFailureError(ErrorCode.MEDIA_RENDER_FAILED, retryable=False)
        final_candidate = root / f"{uuid4().hex}.mp4"
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.runtime.deadline_seconds
        try:
            intermediates: list[Path] = []
            total_units = len(manifest.items) + 1
            for index, item in enumerate(manifest.items):
                image = await self._resolve_source(item.storyboard, context)
                audio = await self._resolve_source(item.dialogue, context)
                intermediate = run_root / f"{index:04d}.mkv"
                await self._run(
                    self._shot_command(image, audio, intermediate, item.duration_ms),
                    context,
                    deadline,
                    cwd=run_root,
                )
                intermediates.append(intermediate)
                await context.report_progress(Progress(index + 1, total_units, "rendering_shots"))
            concat_file = run_root / "concat.txt"
            concat_file.write_text(
                "".join(f"file '{path.name}'\n" for path in intermediates), encoding="utf-8"
            )
            concat_command = self._concat_command(
                concat_file,
                final_candidate,
                manifest.total_duration_ms,
            )
            await self._run(concat_command, context, deadline, cwd=run_root)
            await self._probe(final_candidate, manifest)
            await context.report_progress(Progress(total_units, total_units, "validating_output"))
            return BackendOutput(
                temporary_path=final_candidate,
                resolution=request.resolution,
                frame_count=request.frame_count,
                duration_seconds=manifest.total_duration_ms / 1000,
            )
        except BaseException:
            final_candidate.unlink(missing_ok=True)
            raise
        finally:
            await asyncio.to_thread(shutil.rmtree, run_root, True)
