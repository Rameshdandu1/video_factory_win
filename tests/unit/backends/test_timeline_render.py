from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from video_app.backends.timeline_render import (
    FfmpegTimelineRenderBackend,
    TimelineRenderRuntime,
)
from video_app.domain.models import (
    Resolution,
    TimelineRenderCaption,
    TimelineRenderItem,
    TimelineRenderManifest,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _backend(tmp_path: Path) -> FfmpegTimelineRenderBackend:
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffprobe = tmp_path / "ffprobe.exe"
    font = tmp_path / "telugu.ttf"
    ffmpeg.write_bytes(b"ffmpeg")
    ffprobe.write_bytes(b"ffprobe")
    font.write_bytes(b"font")

    def version(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        line = "ffprobe version approved" if "ffprobe" in command[0] else "ffmpeg version approved"
        return subprocess.CompletedProcess(command, 0, stdout=f"{line}\n", stderr="")

    with patch("video_app.backends.timeline_render.subprocess.run", side_effect=version):
        runtime = TimelineRenderRuntime(
            ffmpeg,
            _sha(ffmpeg),
            "ffmpeg version approved",
            ffprobe,
            _sha(ffprobe),
            "ffprobe version approved",
            font,
            _sha(font),
            "Noto Sans Telugu",
            tmp_path,
            Resolution(1280, 720),
            24,
            1,
            24,
            1_000,
            60,
        )
    return FfmpegTimelineRenderBackend(runtime)


def test_commands_keep_text_out_of_arguments_and_audio_explicit(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    manifest = TimelineRenderManifest.create(
        owner_id="owner",
        project_id="project",
        timeline_id="timeline",
        timeline_revision=1,
        timeline_fingerprint="a" * 64,
        width=1280,
        height=720,
        fps_numerator=24,
        fps_denominator=1,
        total_duration_ms=1_000,
        required_backend="ffmpeg-timeline-render",
        required_backend_revision="ffmpeg-timeline-render-v1",
        items=(TimelineRenderItem("title_card", 0, 1_000, 0, text="తెలుగు,{unsafe}"),),
        captions=(TimelineRenderCaption(0, 900, "caption\\line"),),
    )
    ass = tmp_path / "overlay.ass"
    backend._write_ass(manifest, ass)
    text = ass.read_text(encoding="utf-8")
    assert "తెలుగు" in text
    assert r"\{unsafe\}" in text

    command = backend._final_command(
        tmp_path / "visual.mkv",
        ((tmp_path / "dialogue.wav", 125, 500),),
        tmp_path / "final.mp4",
    )
    assert command.count("-i") == 2
    assert "adelay=125|125" in command[command.index("-filter_complex") + 1]
    assert "తెలుగు" not in " ".join(command)
    assert "aac" in command


def test_runtime_rejects_changed_font_bytes(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    backend.runtime.font_file.write_bytes(b"changed")

    def version(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        line = "ffprobe version approved" if "ffprobe" in command[0] else "ffmpeg version approved"
        return subprocess.CompletedProcess(command, 0, stdout=f"{line}\n", stderr="")

    with (
        patch("video_app.backends.timeline_render.subprocess.run", side_effect=version),
        pytest.raises(ValueError, match="font does not match qualification"),
    ):
        TimelineRenderRuntime(
            backend.runtime.ffmpeg_executable,
            backend.runtime.ffmpeg_sha256,
            backend.runtime.ffmpeg_version_line,
            backend.runtime.ffprobe_executable,
            backend.runtime.ffprobe_sha256,
            backend.runtime.ffprobe_version_line,
            backend.runtime.font_file,
            hashlib.sha256(b"font").hexdigest(),
            "Noto Sans Telugu",
            tmp_path,
            Resolution(1280, 720),
            24,
            1,
            24,
            1_000,
            60,
        )
