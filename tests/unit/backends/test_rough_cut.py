from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from video_app.backends.rough_cut import FfmpegRoughCutBackend, RoughCutRuntime
from video_app.domain.models import Resolution


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _backend(tmp_path: Path) -> FfmpegRoughCutBackend:
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffprobe = tmp_path / "ffprobe.exe"
    ffmpeg.write_bytes(b"ffmpeg")
    ffprobe.write_bytes(b"ffprobe")

    def version(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        line = "ffprobe version approved" if "ffprobe" in command[0] else "ffmpeg version approved"
        return subprocess.CompletedProcess(command, 0, stdout=f"{line}\n", stderr="")

    with patch("video_app.backends.rough_cut.subprocess.run", side_effect=version):
        runtime = RoughCutRuntime(
            ffmpeg,
            _sha(ffmpeg),
            "ffmpeg version approved",
            ffprobe,
            _sha(ffprobe),
            "ffprobe version approved",
            tmp_path,
            Resolution(1280, 720),
            24,
            1,
            21_600,
            60,
        )
    return FfmpegRoughCutBackend(runtime)


def test_shot_command_keeps_image_and_audio_roles_and_fixed_output_policy(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    command = backend._shot_command(
        tmp_path / "storyboard.png",
        tmp_path / "dialogue.wav",
        tmp_path / "shot.mkv",
        10_000,
    )

    assert command[0] == str(backend.runtime.ffmpeg_executable)
    assert "-nostdin" in command
    assert command.count("-i") == 2
    assert command[command.index("-i") + 1].endswith("storyboard.png")
    second_input = command.index("-i", command.index("-i") + 1)
    assert command[second_input + 1].endswith("dialogue.wav")
    assert "libx264" in command
    assert "pcm_s16le" in command
    assert "matroska" in command
    assert "shell" not in command

    concat = backend._concat_command(
        tmp_path / "concat.txt",
        tmp_path / "rough-cut.mp4",
        900_000,
    )
    assert "copy" in concat
    assert "aac" in concat
    assert concat[concat.index("-t") + 1] == "900.000"


def test_runtime_rejects_changed_executable_bytes(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    backend.runtime.ffmpeg_executable.write_bytes(b"changed")
    with (
        patch("video_app.backends.rough_cut.subprocess.run"),
        pytest.raises(ValueError, match="does not match qualification"),
    ):
        RoughCutRuntime(
            backend.runtime.ffmpeg_executable,
            hashlib.sha256(b"ffmpeg").hexdigest(),
            "ffmpeg version approved",
            backend.runtime.ffprobe_executable,
            backend.runtime.ffprobe_sha256,
            backend.runtime.ffprobe_version_line,
            tmp_path,
            Resolution(1280, 720),
            24,
            1,
            21_600,
            60,
        )
