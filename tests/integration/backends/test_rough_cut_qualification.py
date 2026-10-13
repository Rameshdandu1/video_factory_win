from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import pytest

from video_app.backends.rough_cut import (
    ROUGH_CUT_BACKEND_NAME,
    ROUGH_CUT_BACKEND_REVISION,
    FfmpegRoughCutBackend,
    RoughCutRuntime,
)
from video_app.domain.models import (
    BackendOutput,
    ErrorCode,
    GenerationMode,
    GenerationRequest,
    Progress,
    Resolution,
    RoughCutItem,
    RoughCutManifest,
    RoughCutSource,
)
from video_app.domain.ports import BackendCancelledError, BackendFailureError, GenerationContext

_RUN = os.environ.get("VIDEO_APP_RUN_ROUGH_CUT_QUALIFICATION") == "1"


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise AssertionError(f"{name} must be configured")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _version_line(path: Path) -> str:
    expected = _required(
        "VIDEO_APP_ROUGH_CUT_FFMPEG_VERSION_LINE"
        if path.name.lower().startswith("ffmpeg")
        else "VIDEO_APP_FFPROBE_VERSION_LINE"
    )
    return expected


def _request(
    *,
    image: Path,
    audio: Path,
    resolution: Resolution,
    fps_numerator: int,
    fps_denominator: int,
    duration_ms: int,
    dialogue_sha256: str | None = None,
) -> GenerationRequest:
    item = RoughCutItem(
        scene_id="qualification-scene",
        scene_version=1,
        scene_fingerprint=hashlib.sha256(b"qualification-scene").hexdigest(),
        scene_position=0,
        shot_id="qualification-shot",
        shot_version=1,
        shot_fingerprint=hashlib.sha256(b"qualification-shot").hexdigest(),
        shot_position=0,
        duration_ms=duration_ms,
        storyboard=RoughCutSource("image", 1, _sha256(image), "qualification/image"),
        dialogue=RoughCutSource(
            "audio",
            1,
            _sha256(audio) if dialogue_sha256 is None else dialogue_sha256,
            "qualification/audio",
        ),
    )
    manifest = RoughCutManifest.create(
        owner_id="qualification",
        project_id="qualification",
        workspace_fingerprint=hashlib.sha256(b"qualification-workspace").hexdigest(),
        width=resolution.width,
        height=resolution.height,
        fps_numerator=fps_numerator,
        fps_denominator=fps_denominator,
        total_duration_ms=duration_ms,
        required_backend=ROUGH_CUT_BACKEND_NAME,
        required_backend_revision=ROUGH_CUT_BACKEND_REVISION,
        items=(item,),
    )
    return GenerationRequest(
        prompt="Approved qualification rough cut",
        model=ROUGH_CUT_BACKEND_NAME,
        resolution=resolution,
        frame_count=manifest.frame_count,
        seed=0,
        mode=GenerationMode.ROUGH_CUT,
        rough_cut=manifest,
    )


@pytest.mark.integration
@unittest.skipUnless(
    _RUN,
    "set VIDEO_APP_RUN_ROUGH_CUT_QUALIFICATION=1 for explicit FFmpeg qualification",
)
class RoughCutQualificationTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_export_hash_enforcement_and_cancellation_write_report(self) -> None:
        ffmpeg = Path(_required("VIDEO_APP_ROUGH_CUT_FFMPEG_EXECUTABLE")).resolve(strict=True)
        ffprobe = Path(_required("VIDEO_APP_FFPROBE_EXECUTABLE")).resolve(strict=True)
        image = Path(_required("VIDEO_APP_ROUGH_CUT_QUALIFICATION_IMAGE")).resolve(strict=True)
        audio = Path(_required("VIDEO_APP_ROUGH_CUT_QUALIFICATION_AUDIO")).resolve(strict=True)
        report_dir = Path(_required("VIDEO_APP_ROUGH_CUT_QUALIFICATION_DIR")).resolve(strict=True)
        ffmpeg_sha256 = _required("VIDEO_APP_ROUGH_CUT_FFMPEG_SHA256")
        ffprobe_sha256 = _required("VIDEO_APP_FFPROBE_SHA256")
        width = int(os.environ.get("VIDEO_APP_ROUGH_CUT_WIDTH", "1280"))
        height = int(os.environ.get("VIDEO_APP_ROUGH_CUT_HEIGHT", "720"))
        fps_numerator = int(os.environ.get("VIDEO_APP_ROUGH_CUT_FPS_NUMERATOR", "24"))
        fps_denominator = int(os.environ.get("VIDEO_APP_ROUGH_CUT_FPS_DENOMINATOR", "1"))
        duration_ms = 2_000
        resolution = Resolution(width, height)
        self.assertEqual(_sha256(ffmpeg), ffmpeg_sha256)
        self.assertEqual(_sha256(ffprobe), ffprobe_sha256)

        with tempfile.TemporaryDirectory(dir=report_dir, prefix="rough-cut-qualification-") as name:
            output_root = Path(name).resolve(strict=True)
            backend = FfmpegRoughCutBackend(
                RoughCutRuntime(
                    ffmpeg_executable=ffmpeg,
                    ffmpeg_sha256=ffmpeg_sha256,
                    ffmpeg_version_line=_version_line(ffmpeg),
                    ffprobe_executable=ffprobe,
                    ffprobe_sha256=ffprobe_sha256,
                    ffprobe_version_line=_version_line(ffprobe),
                    output_root=output_root,
                    resolution=resolution,
                    fps_numerator=fps_numerator,
                    fps_denominator=fps_denominator,
                    frame_count=duration_ms * fps_numerator // (1_000 * fps_denominator),
                    deadline_seconds=120,
                    cancellation_poll_seconds=0.05,
                    termination_grace_seconds=5,
                )
            )

            async def run(request: GenerationRequest, cancellation: asyncio.Event) -> BackendOutput:
                async def report(_: Progress) -> None:
                    return None

                async def cancelled() -> bool:
                    return cancellation.is_set()

                async def resolve(storage_key: str) -> Path:
                    return image if storage_key.endswith("image") else audio

                return await backend.generate(
                    request,
                    GenerationContext("qualification", report, cancelled, resolve),
                )

            request = _request(
                image=image,
                audio=audio,
                resolution=resolution,
                fps_numerator=fps_numerator,
                fps_denominator=fps_denominator,
                duration_ms=duration_ms,
            )
            output = await run(request, asyncio.Event())
            self.assertEqual(output.frame_count, request.frame_count)
            self.assertEqual(output.resolution, resolution)
            self.assertTrue(output.temporary_path.is_file())
            output.temporary_path.unlink()

            changed_request = _request(
                image=image,
                audio=audio,
                resolution=resolution,
                fps_numerator=fps_numerator,
                fps_denominator=fps_denominator,
                duration_ms=duration_ms,
                dialogue_sha256="0" * 64,
            )
            with self.assertRaises(BackendFailureError) as raised:
                await run(changed_request, asyncio.Event())
            self.assertEqual(raised.exception.code, ErrorCode.MEDIA_RENDER_FAILED)

            cancellation = asyncio.Event()
            cancellation.set()
            with self.assertRaises(BackendCancelledError):
                await run(request, cancellation)
            self.assertEqual(list(output_root.iterdir()), [])

        report_payload = {
            "schema_version": "rough-cut-qualification-v1",
            "status": "approved",
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "backend_revision": ROUGH_CUT_BACKEND_REVISION,
            "ffmpeg_sha256": ffmpeg_sha256,
            "ffmpeg_version_line": _version_line(ffmpeg),
            "ffprobe_sha256": ffprobe_sha256,
            "ffprobe_version_line": _version_line(ffprobe),
            "width": width,
            "height": height,
            "fps_numerator": fps_numerator,
            "fps_denominator": fps_denominator,
            "image_sha256": _sha256(image),
            "audio_sha256": _sha256(audio),
            "image_audio_export_verified": True,
            "measured_output_verified": True,
            "input_hash_enforcement_verified": True,
            "cancellation_cleanup_verified": True,
        }
        target = report_dir / "rough-cut-qualification.json"
        partial = report_dir / ".rough-cut-qualification.part"
        partial.write_text(
            json.dumps(report_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(partial, target)
