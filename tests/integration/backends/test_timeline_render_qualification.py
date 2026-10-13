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

from video_app.backends.timeline_render import (
    TIMELINE_RENDER_BACKEND_NAME,
    TIMELINE_RENDER_BACKEND_REVISION,
    FfmpegTimelineRenderBackend,
    TimelineRenderRuntime,
)
from video_app.domain.models import (
    BackendOutput,
    ErrorCode,
    GenerationMode,
    GenerationRequest,
    Progress,
    Resolution,
    TimelineRenderCaption,
    TimelineRenderItem,
    TimelineRenderManifest,
    TimelineRenderSource,
)
from video_app.domain.ports import BackendCancelledError, BackendFailureError, GenerationContext

_RUN = os.environ.get("VIDEO_APP_RUN_TIMELINE_RENDER_QUALIFICATION") == "1"


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


def _request(
    *,
    audio: Path,
    resolution: Resolution,
    fps_numerator: int,
    fps_denominator: int,
    duration_ms: int,
    audio_sha256: str | None = None,
) -> GenerationRequest:
    manifest = TimelineRenderManifest.create(
        owner_id="qualification",
        project_id="qualification",
        timeline_id="qualification",
        timeline_revision=1,
        timeline_fingerprint=hashlib.sha256(b"qualification-timeline").hexdigest(),
        width=resolution.width,
        height=resolution.height,
        fps_numerator=fps_numerator,
        fps_denominator=fps_denominator,
        total_duration_ms=duration_ms,
        required_backend=TIMELINE_RENDER_BACKEND_NAME,
        required_backend_revision=TIMELINE_RENDER_BACKEND_REVISION,
        items=(
            TimelineRenderItem(
                "title_card",
                0,
                duration_ms,
                0,
                text="తెలుగు తుది రెండర్",
            ),
            TimelineRenderItem(
                "audio",
                0,
                duration_ms,
                1,
                source=TimelineRenderSource(
                    "audio",
                    1,
                    _sha256(audio) if audio_sha256 is None else audio_sha256,
                    "qualification/audio",
                    "audio",
                    duration_ms,
                ),
            ),
        ),
        captions=(TimelineRenderCaption(250, min(duration_ms, 3_000), "తెలుగు ఉపశీర్షిక"),),
    )
    return GenerationRequest(
        "Approved qualification timeline",
        TIMELINE_RENDER_BACKEND_NAME,
        resolution,
        manifest.frame_count,
        0,
        GenerationMode.TIMELINE_RENDER,
        timeline_render=manifest,
    )


@pytest.mark.integration
@unittest.skipUnless(
    _RUN,
    "set VIDEO_APP_RUN_TIMELINE_RENDER_QUALIFICATION=1 for explicit FFmpeg qualification",
)
class TimelineRenderQualificationTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_export_hash_enforcement_and_cancellation_write_review_draft(self) -> None:
        ffmpeg = Path(_required("VIDEO_APP_TIMELINE_RENDER_FFMPEG_EXECUTABLE")).resolve(strict=True)
        ffprobe = Path(_required("VIDEO_APP_FFPROBE_EXECUTABLE")).resolve(strict=True)
        font = Path(_required("VIDEO_APP_TIMELINE_RENDER_FONT_FILE")).resolve(strict=True)
        audio = Path(_required("VIDEO_APP_TIMELINE_RENDER_QUALIFICATION_AUDIO")).resolve(
            strict=True
        )
        report_dir = Path(_required("VIDEO_APP_TIMELINE_RENDER_QUALIFICATION_DIR")).resolve(
            strict=True
        )
        ffmpeg_sha256 = _required("VIDEO_APP_TIMELINE_RENDER_FFMPEG_SHA256")
        ffprobe_sha256 = _required("VIDEO_APP_FFPROBE_SHA256")
        font_sha256 = _required("VIDEO_APP_TIMELINE_RENDER_FONT_SHA256")
        font_family = _required("VIDEO_APP_TIMELINE_RENDER_FONT_FAMILY")
        ffmpeg_version = _required("VIDEO_APP_TIMELINE_RENDER_FFMPEG_VERSION_LINE")
        ffprobe_version = _required("VIDEO_APP_FFPROBE_VERSION_LINE")
        width = int(os.environ.get("VIDEO_APP_TIMELINE_RENDER_WIDTH", "1280"))
        height = int(os.environ.get("VIDEO_APP_TIMELINE_RENDER_HEIGHT", "720"))
        fps_numerator = int(os.environ.get("VIDEO_APP_TIMELINE_RENDER_FPS_NUMERATOR", "24"))
        fps_denominator = int(os.environ.get("VIDEO_APP_TIMELINE_RENDER_FPS_DENOMINATOR", "1"))
        duration_ms = int(os.environ.get("VIDEO_APP_TIMELINE_RENDER_DURATION_MS", "900000"))
        resolution = Resolution(width, height)
        self.assertEqual(_sha256(ffmpeg), ffmpeg_sha256)
        self.assertEqual(_sha256(ffprobe), ffprobe_sha256)
        self.assertEqual(_sha256(font), font_sha256)

        with tempfile.TemporaryDirectory(
            dir=report_dir, prefix="timeline-render-qualification-"
        ) as name:
            output_root = Path(name).resolve(strict=True)
            backend = FfmpegTimelineRenderBackend(
                TimelineRenderRuntime(
                    ffmpeg,
                    ffmpeg_sha256,
                    ffmpeg_version,
                    ffprobe,
                    ffprobe_sha256,
                    ffprobe_version,
                    font,
                    font_sha256,
                    font_family,
                    output_root,
                    resolution,
                    fps_numerator,
                    fps_denominator,
                    duration_ms * fps_numerator // (1_000 * fps_denominator),
                    duration_ms,
                    14_400,
                    cancellation_poll_seconds=0.05,
                    termination_grace_seconds=5,
                )
            )

            async def run(request: GenerationRequest, cancellation: asyncio.Event) -> BackendOutput:
                async def report(_: Progress) -> None:
                    return None

                async def cancelled() -> bool:
                    return cancellation.is_set()

                async def resolve(_: str) -> Path:
                    return audio

                return await backend.generate(
                    request,
                    GenerationContext("qualification", report, cancelled, resolve),
                )

            request = _request(
                audio=audio,
                resolution=resolution,
                fps_numerator=fps_numerator,
                fps_denominator=fps_denominator,
                duration_ms=duration_ms,
            )
            output = await run(request, asyncio.Event())
            review_copy = report_dir / "timeline-render-review.mp4"
            os.replace(output.temporary_path, review_copy)

            changed = _request(
                audio=audio,
                resolution=resolution,
                fps_numerator=fps_numerator,
                fps_denominator=fps_denominator,
                duration_ms=duration_ms,
                audio_sha256="0" * 64,
            )
            with self.assertRaises(BackendFailureError) as raised:
                await run(changed, asyncio.Event())
            self.assertEqual(raised.exception.code, ErrorCode.MEDIA_RENDER_FAILED)

            cancellation = asyncio.Event()
            cancellation.set()
            with self.assertRaises(BackendCancelledError):
                await run(request, cancellation)
            self.assertEqual(list(output_root.iterdir()), [])

        report_payload = {
            "schema_version": "timeline-render-qualification-v1",
            "status": "pending_operator_review",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "backend_revision": TIMELINE_RENDER_BACKEND_REVISION,
            "ffmpeg_sha256": ffmpeg_sha256,
            "ffmpeg_version_line": ffmpeg_version,
            "ffprobe_sha256": ffprobe_sha256,
            "ffprobe_version_line": ffprobe_version,
            "font_sha256": font_sha256,
            "font_family": font_family,
            "width": width,
            "height": height,
            "fps_numerator": fps_numerator,
            "fps_denominator": fps_denominator,
            "duration_ms": duration_ms,
            "audio_sha256": _sha256(audio),
            "title_caption_verified": False,
            "telugu_glyphs_verified": False,
            "audio_mix_verified": False,
            "measured_output_verified": True,
            "input_hash_enforcement_verified": True,
            "cancellation_cleanup_verified": True,
            "review_media": str(review_copy),
        }
        target = report_dir / "timeline-render-qualification.draft.json"
        partial = report_dir / ".timeline-render-qualification.part"
        partial.write_text(
            json.dumps(report_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(partial, target)
