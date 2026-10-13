from datetime import datetime, timezone

from video_app.api.timeline_render_models import TimelineRenderJobModel
from video_app.domain.jobs import GenerationJob
from video_app.domain.models import (
    GenerationMode,
    GenerationRequest,
    Resolution,
    TimelineRenderItem,
    TimelineRenderManifest,
)


def test_transport_exposes_provenance_without_private_storage_keys() -> None:
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
        items=(TimelineRenderItem("title_card", 0, 1_000, 0, text="Title"),),
        captions=(),
    )
    request = GenerationRequest(
        "Approved timeline",
        "ffmpeg-timeline-render",
        Resolution(1280, 720),
        24,
        0,
        GenerationMode.TIMELINE_RENDER,
        timeline_render=manifest,
    )
    job = GenerationJob.queued(
        "job",
        request,
        datetime(2026, 10, 13, tzinfo=timezone.utc),
        idempotency_key="key",
    )

    payload = TimelineRenderJobModel.from_domain(job).model_dump()

    assert payload["timeline_fingerprint"] == "a" * 64
    assert payload["visual_item_count"] == 1
    assert "storage_key" not in str(payload)
