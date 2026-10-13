"""Pinned FFmpeg adapter for immutable approved timeline manifests."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
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
    TimelineRenderManifest,
    TimelineRenderSource,
)
from video_app.domain.ports import BackendCancelledError, BackendFailureError, GenerationContext

TIMELINE_RENDER_BACKEND_NAME = "ffmpeg-timeline-render"
TIMELINE_RENDER_BACKEND_REVISION = "ffmpeg-timeline-render-v1"
_FONT_FAMILY = re.compile(r"[A-Za-z0-9 _-]{1,80}")


class TimelineRenderConfigurationError(ValueError):
    """Raised when a media runtime differs from its reviewed pins."""


def _is_link(path: Path) -> bool:
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return path.is_symlink() or bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _regular_file(path: Path, field: str) -> Path:
    if not path.is_absolute() or not path.is_file() or _is_link(path):
        raise TimelineRenderConfigurationError(f"{field} must be an existing absolute regular file")
    return path.resolve(strict=True)


def _regular_directory(path: Path, field: str) -> Path:
    if not path.is_absolute() or not path.is_dir() or _is_link(path):
        raise TimelineRenderConfigurationError(
            f"{field} must be an existing absolute regular directory"
        )
    return path.resolve(strict=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_sha256(value: str, field: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise TimelineRenderConfigurationError(f"{field} must be lowercase SHA-256")


def _verify_executable(path: Path, sha256: str, version_line: str, name: str) -> Path:
    executable = _regular_file(path, name)
    _validate_sha256(sha256, f"{name} checksum")
    if _sha256(executable) != sha256:
        raise TimelineRenderConfigurationError(f"{name} executable does not match qualification")
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
        raise TimelineRenderConfigurationError(f"{name} version could not be verified") from error
    if measured != version_line:
        raise TimelineRenderConfigurationError(f"{name} version does not match qualification")
    return executable


@dataclass(frozen=True, slots=True)
class TimelineRenderRuntime:
    ffmpeg_executable: Path
    ffmpeg_sha256: str
    ffmpeg_version_line: str
    ffprobe_executable: Path
    ffprobe_sha256: str
    ffprobe_version_line: str
    font_file: Path
    font_sha256: str
    font_family: str
    output_root: Path
    resolution: Resolution
    fps_numerator: int
    fps_denominator: int
    frame_count: int
    duration_ms: int
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
        font = _regular_file(self.font_file, "timeline-render font")
        _validate_sha256(self.font_sha256, "timeline-render font checksum")
        if _sha256(font) != self.font_sha256:
            raise TimelineRenderConfigurationError(
                "timeline-render font does not match qualification"
            )
        if _FONT_FAMILY.fullmatch(self.font_family) is None:
            raise TimelineRenderConfigurationError("timeline-render font family is invalid")
        output = _regular_directory(self.output_root, "timeline-render output root")
        if (
            min(
                self.fps_numerator,
                self.fps_denominator,
                self.frame_count,
                self.duration_ms,
                self.deadline_seconds,
            )
            <= 0
        ):
            raise TimelineRenderConfigurationError(
                "timeline-render runtime limits must be positive"
            )
        if self.cancellation_poll_seconds <= 0 or self.termination_grace_seconds <= 0:
            raise TimelineRenderConfigurationError(
                "timeline-render process timing must be positive"
            )
        object.__setattr__(self, "ffmpeg_executable", ffmpeg)
        object.__setattr__(self, "ffprobe_executable", ffprobe)
        object.__setattr__(self, "font_file", font)
        object.__setattr__(self, "output_root", output)


def _ass_time(milliseconds: int) -> str:
    centiseconds = milliseconds // 10
    hours, remainder = divmod(centiseconds, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    seconds, fraction = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{fraction:02d}"


def _ass_text(value: str) -> str:
    return (
        value.replace("\\", r"\\")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("\r\n", r"\N")
        .replace("\r", r"\N")
        .replace("\n", r"\N")
    )


@dataclass(frozen=True, slots=True)
class FfmpegTimelineRenderBackend:
    runtime: TimelineRenderRuntime

    @property
    def name(self) -> str:
        return TIMELINE_RENDER_BACKEND_NAME

    @property
    def revision(self) -> str:
        return TIMELINE_RENDER_BACKEND_REVISION

    def capabilities(self) -> tuple[ModelCapability, ...]:
        return (
            ModelCapability(
                model_id=self.name,
                display_name="Approved final timeline render",
                modes=frozenset({GenerationMode.TIMELINE_RENDER}),
                resolutions=frozenset({self.runtime.resolution}),
                frame_counts=frozenset({self.runtime.frame_count}),
            ),
        )

    def _supports(self, request: GenerationRequest) -> bool:
        manifest = request.timeline_render
        return (
            request.mode is GenerationMode.TIMELINE_RENDER
            and request.model == self.name
            and manifest is not None
            and manifest.required_backend == self.name
            and manifest.required_backend_revision == self.revision
            and request.resolution == self.runtime.resolution
            and manifest.fps_numerator == self.runtime.fps_numerator
            and manifest.fps_denominator == self.runtime.fps_denominator
            and manifest.total_duration_ms == self.runtime.duration_ms
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
                        asyncio.shield(wait),
                        timeout=self.runtime.cancellation_poll_seconds,
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

    async def _resolve_source(
        self, source: TimelineRenderSource, context: GenerationContext
    ) -> Path:
        if context.resolve_input is None:
            raise BackendFailureError(ErrorCode.MEDIA_RENDER_FAILED, retryable=False)
        try:
            path = _regular_file(
                await context.resolve_input(source.storage_key), "timeline-render input"
            )
            measured = await asyncio.to_thread(_sha256, path)
        except (OSError, ValueError, TimelineRenderConfigurationError) as error:
            raise BackendFailureError(ErrorCode.MEDIA_RENDER_FAILED, retryable=False) from error
        if measured != source.sha256:
            raise BackendFailureError(ErrorCode.MEDIA_RENDER_FAILED, retryable=False)
        return path

    def _visual_command(
        self,
        kind: str,
        source: Path | None,
        destination: Path,
        duration_ms: int,
    ) -> tuple[str, ...]:
        duration = f"{duration_ms / 1000:.3f}"
        fps = f"{self.runtime.fps_numerator}/{self.runtime.fps_denominator}"
        width = self.runtime.resolution.width
        height = self.runtime.resolution.height
        normalize = (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"setsar=1,fps={fps},format=yuv420p"
        )
        command: list[str] = [
            str(self.runtime.ffmpeg_executable),
            "-nostdin",
            "-v",
            "error",
        ]
        if kind == "image":
            assert source is not None
            command.extend(["-loop", "1", "-framerate", fps, "-i", str(source)])
        elif kind == "video":
            assert source is not None
            command.extend(["-i", str(source)])
        else:
            command.extend(["-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:r={fps}"])
        command.extend(
            [
                "-vf",
                normalize,
                "-t",
                duration,
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-threads",
                "1",
                "-map_metadata",
                "-1",
                "-f",
                "matroska",
                "-y",
                str(destination),
            ]
        )
        return tuple(command)

    def _concat_command(self, concat_file: Path, destination: Path) -> tuple[str, ...]:
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
            "-c:v",
            "copy",
            "-an",
            "-map_metadata",
            "-1",
            "-f",
            "matroska",
            "-y",
            str(destination),
        )

    def _write_ass(self, manifest: TimelineRenderManifest, destination: Path) -> None:
        width = manifest.width
        height = manifest.height
        lines = [
            "[Script Info]",
            "ScriptType: v4.00+",
            f"PlayResX: {width}",
            f"PlayResY: {height}",
            "WrapStyle: 0",
            "ScaledBorderAndShadow: yes",
            "",
            "[V4+ Styles]",
            "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,"
            "BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,"
            "BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
            f"Style: Caption,{self.runtime.font_family},42,&H00FFFFFF,&H000000FF,"
            "&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,1,2,80,80,48,1",
            f"Style: Title,{self.runtime.font_family},64,&H00FFFFFF,&H000000FF,"
            "&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,1,5,80,80,48,1",
            "",
            "[Events]",
            "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
        ]
        for item in manifest.items:
            if item.kind == "title_card":
                assert item.text is not None
                lines.append(
                    "Dialogue: 0,"
                    f"{_ass_time(item.start_ms)},{_ass_time(item.start_ms + item.duration_ms)},"
                    f"Title,,0,0,0,,{_ass_text(item.text.strip())}"
                )
        for caption in manifest.captions:
            lines.append(
                "Dialogue: 1,"
                f"{_ass_time(caption.start_ms)},{_ass_time(caption.end_ms)},"
                f"Caption,,0,0,0,,{_ass_text(caption.text.strip())}"
            )
        destination.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _final_command(
        self,
        visual: Path,
        audio: tuple[tuple[Path, int, int], ...],
        destination: Path,
    ) -> tuple[str, ...]:
        total = f"{self.runtime.duration_ms / 1000:.3f}"
        command: list[str] = [
            str(self.runtime.ffmpeg_executable),
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(visual),
        ]
        for source, _start_ms, _duration_ms in audio:
            command.extend(["-i", str(source)])
        filters = ["[0:v]ass=overlay.ass:fontsdir=.[v]"]
        if audio:
            names: list[str] = []
            for index, (_source, start_ms, duration_ms) in enumerate(audio, start=1):
                name = f"a{index}"
                filters.append(
                    f"[{index}:a]atrim=0:{duration_ms / 1000:.3f},"
                    f"asetpts=PTS-STARTPTS,aresample=48000,adelay={start_ms}|{start_ms}[{name}]"
                )
                names.append(f"[{name}]")
            filters.append(
                f"{''.join(names)}amix=inputs={len(names)}:normalize=0:dropout_transition=0,"
                f"apad,atrim=0:{total}[a]"
            )
        else:
            command.extend(
                [
                    "-f",
                    "lavfi",
                    "-t",
                    total,
                    "-i",
                    "anullsrc=channel_layout=stereo:sample_rate=48000",
                ]
            )
            filters.append("[1:a]atrim=0:" + total + "[a]")
        command.extend(
            [
                "-filter_complex",
                ";".join(filters),
                "-map",
                "[v]",
                "-map",
                "[a]",
                "-t",
                total,
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-threads",
                "1",
                "-map_metadata",
                "-1",
                "-movflags",
                "+faststart",
                "-y",
                str(destination),
            ]
        )
        return tuple(command)

    async def _probe(self, output: Path, manifest: TimelineRenderManifest) -> None:
        command = (
            str(self.runtime.ffprobe_executable),
            "-v",
            "error",
            "-count_frames",
            "-show_entries",
            "stream=codec_type,width,height,nb_read_frames,sample_rate,channels:format=duration",
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
            streams = cast(list[dict[str, object]], payload["streams"])
            video = next(item for item in streams if item["codec_type"] == "video")
            audio = next(item for item in streams if item["codec_type"] == "audio")
            duration = float(payload["format"]["duration"])
            if (
                int(cast(str | int, video["width"])) != manifest.width
                or int(cast(str | int, video["height"])) != manifest.height
                or int(cast(str | int, video["nb_read_frames"])) != manifest.frame_count
                or int(cast(str | int, audio["sample_rate"])) != 48_000
                or int(cast(str | int, audio["channels"])) != 2
                or abs(duration - manifest.total_duration_ms / 1000) > 0.05
            ):
                raise ValueError("timeline-render output does not match its manifest")
        except (
            OSError,
            subprocess.SubprocessError,
            StopIteration,
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
        manifest = request.timeline_render
        assert manifest is not None
        root = self.runtime.output_root.resolve(strict=True)
        run_root = root / f"timeline-render-{uuid4().hex}"
        run_root.mkdir()
        if run_root.parent != root or _is_link(run_root):
            raise BackendFailureError(ErrorCode.MEDIA_RENDER_FAILED, retryable=False)
        final_candidate = root / f"{uuid4().hex}.mp4"
        deadline = asyncio.get_running_loop().time() + self.runtime.deadline_seconds
        try:
            font_copy = run_root / "font.ttf"
            shutil.copyfile(self.runtime.font_file, font_copy)
            if await asyncio.to_thread(_sha256, font_copy) != self.runtime.font_sha256:
                raise BackendFailureError(ErrorCode.MEDIA_RENDER_FAILED, retryable=False)
            self._write_ass(manifest, run_root / "overlay.ass")
            visual_items = tuple(item for item in manifest.items if item.kind != "audio")
            audio_items = tuple(item for item in manifest.items if item.kind == "audio")
            intermediates: list[Path] = []
            total_units = len(visual_items) + 2
            for index, item in enumerate(visual_items):
                source = (
                    None
                    if item.source is None
                    else await self._resolve_source(item.source, context)
                )
                intermediate = run_root / f"visual-{index:04d}.mkv"
                await self._run(
                    self._visual_command(item.kind, source, intermediate, item.duration_ms),
                    context,
                    deadline,
                    cwd=run_root,
                )
                intermediates.append(intermediate)
                await context.report_progress(
                    Progress(index + 1, total_units, "normalizing_visuals")
                )
            concat_file = run_root / "concat.txt"
            concat_file.write_text(
                "".join(f"file '{path.name}'\n" for path in intermediates),
                encoding="utf-8",
            )
            visual = run_root / "visual.mkv"
            await self._run(
                self._concat_command(concat_file, visual),
                context,
                deadline,
                cwd=run_root,
            )
            await context.report_progress(
                Progress(len(visual_items) + 1, total_units, "mixing_and_captioning")
            )
            audio_sources: list[tuple[Path, int, int]] = []
            for item in audio_items:
                assert item.source is not None
                audio_sources.append(
                    (
                        await self._resolve_source(item.source, context),
                        item.start_ms,
                        item.duration_ms,
                    )
                )
            await self._run(
                self._final_command(visual, tuple(audio_sources), final_candidate),
                context,
                deadline,
                cwd=run_root,
            )
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
