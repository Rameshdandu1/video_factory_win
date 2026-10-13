from __future__ import annotations

from datetime import datetime, timezone

from video_app.api.rough_cut_models import RoughCutJobModel
from video_app.domain.jobs import GenerationJob
from video_app.domain.models import (
    GenerationMode,
    GenerationRequest,
    Resolution,
    RoughCutItem,
    RoughCutManifest,
    RoughCutSource,
)


def test_rough_cut_transport_exposes_provenance_without_storage_keys() -> None:
    source = RoughCutSource("asset", 1, "a" * 64, "uploads/private.png")
    item = RoughCutItem(
        "scene",
        1,
        "b" * 64,
        0,
        "shot",
        1,
        "c" * 64,
        0,
        1_000,
        source,
        RoughCutSource("audio", 2, "d" * 64, "uploads/private.wav"),
    )
    manifest = RoughCutManifest.create(
        owner_id="owner",
        project_id="project",
        workspace_fingerprint="e" * 64,
        width=1280,
        height=720,
        fps_numerator=24,
        fps_denominator=1,
        total_duration_ms=1_000,
        required_backend="ffmpeg-rough-cut",
        required_backend_revision="ffmpeg-rough-cut-v1",
        items=(item,),
    )
    request = GenerationRequest(
        "Approved rough cut",
        "ffmpeg-rough-cut",
        Resolution(1280, 720),
        24,
        0,
        GenerationMode.ROUGH_CUT,
        rough_cut=manifest,
    )
    job = GenerationJob.queued(
        "job", request, datetime(2026, 10, 13, tzinfo=timezone.utc), idempotency_key="key"
    )

    payload = RoughCutJobModel.from_domain(job).model_dump()

    assert payload["manifest_fingerprint"] == manifest.manifest_fingerprint
    assert payload["shot_count"] == 1
    assert "storage_key" not in str(payload)
    assert "private" not in str(payload)
