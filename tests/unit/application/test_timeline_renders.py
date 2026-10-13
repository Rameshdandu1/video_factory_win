from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import cast

import pytest

from video_app.application.assets import AssetRepository
from video_app.application.ports import Clock, IdentifierFactory, JobRepository
from video_app.application.projects import ProjectRepository
from video_app.application.timeline_renders import SubmitTimelineRender, TimelineRenderProvider
from video_app.application.timelines import TimelineRepository
from video_app.domain.assets import (
    AssetKind,
    AssetState,
    MediaAsset,
    MediaMetadata,
    RightsDeclaration,
)
from video_app.domain.jobs import GenerationJob
from video_app.domain.models import DomainValidationError, GenerationMode
from video_app.domain.projects import (
    AspectRatio,
    BudgetPolicy,
    ExportSettings,
    Project,
    ProjectDraft,
    ProjectMode,
    ProviderSelections,
)
from video_app.domain.timelines import (
    CaptionSegment,
    TimelineDraft,
    TimelineItem,
    TimelineItemKind,
    TimelineRevision,
)

NOW = datetime(2026, 10, 13, tzinfo=timezone.utc)


class Fixtures:
    def __init__(self, project: Project, timeline: TimelineRevision) -> None:
        self.project = project
        self.timeline = timeline
        self.assets = {
            "image": _asset("image", AssetKind.IMAGE),
            "audio": _asset("audio", AssetKind.AUDIO),
        }
        self.enqueued: list[GenerationJob] = []

    async def get(self, owner_id: str, project_id: str, item_id: str | None = None) -> object:
        assert owner_id == "owner" and project_id == "project"
        if item_id is None:
            return self.project
        if item_id == "timeline":
            return self.timeline
        return self.assets[item_id]

    async def enqueue(self, job: GenerationJob) -> GenerationJob:
        self.enqueued.append(job)
        return job


class FixedClock:
    def now(self) -> datetime:
        return NOW


class Identifiers:
    def new_job_id(self) -> str:
        return "job_timeline"

    def new_attempt_id(self) -> str:
        return "attempt"

    def new_lease_token(self) -> str:
        return "lease"

    def new_correlation_id(self) -> str:
        return "correlation"


def _asset(asset_id: str, kind: AssetKind) -> MediaAsset:
    metadata = (
        None
        if kind is AssetKind.IMAGE
        else MediaMetadata(
            "wav",
            1_000,
            sample_rate=48_000,
            channels=2,
            sample_count=48_000,
        )
    )
    return MediaAsset(
        id=asset_id,
        project_id="project",
        owner_id="owner",
        version=1,
        kind=kind,
        state=AssetState.READY if metadata is None else AssetState.INSPECTED,
        original_filename=f"{asset_id}.{'png' if metadata is None else 'wav'}",
        media_type="image/png" if metadata is None else "audio/wav",
        storage_key=f"uploads/{asset_id}",
        size_bytes=100,
        sha256=("a" if metadata is None else "b") * 64,
        rights=RightsDeclaration.OWNED,
        created_at=NOW,
        metadata=metadata,
        inspector_revision=None if metadata is None else "ffprobe-v1",
        inspected_at=None if metadata is None else NOW,
    )


def _project() -> Project:
    project = Project.create(
        project_id="project",
        owner_id="owner",
        draft=ProjectDraft(
            "Film",
            "te",
            ProjectMode.SHORT,
            1_000,
            AspectRatio.LANDSCAPE,
            ExportSettings(1280, 720, 24),
            ProviderSelections("wan"),
            BudgetPolicy(),
        ),
        now=NOW,
    )
    return replace(project, approved_timeline_revision_id="timeline")


def _timeline() -> TimelineRevision:
    draft = TimelineDraft(
        1_000,
        (
            TimelineItem(TimelineItemKind.IMAGE, 0, 1_000, 0, asset_id="image"),
            TimelineItem(TimelineItemKind.AUDIO, 0, 1_000, 1, asset_id="audio"),
        ),
        (CaptionSegment(100, 900, "తెలుగు"),),
    )
    return TimelineRevision(
        "timeline",
        "project",
        "owner",
        2,
        draft.duration_ms,
        draft.items,
        draft.captions,
        draft.fingerprint(),
        NOW,
        NOW,
    )


def _submit(fixtures: Fixtures) -> SubmitTimelineRender:
    return SubmitTimelineRender(
        cast(ProjectRepository, fixtures),
        cast(TimelineRepository, fixtures),
        cast(AssetRepository, fixtures),
        cast(JobRepository, fixtures),
        TimelineRenderProvider(
            "ffmpeg-timeline-render",
            "ffmpeg-timeline-render-v1",
            "Final renderer",
            True,
            "qualified",
            1280,
            720,
            24,
            1,
            1_000,
        ),
        cast(Clock, FixedClock()),
        cast(IdentifierFactory, Identifiers()),
        "owner",
    )


@pytest.mark.anyio
async def test_submit_freezes_approved_timeline_assets_audio_and_captions() -> None:
    fixtures = Fixtures(_project(), _timeline())

    job = await _submit(fixtures)("project", "timeline", idempotency_key="final-v1")

    manifest = job.request.timeline_render
    assert job.request.mode is GenerationMode.TIMELINE_RENDER
    assert manifest is not None
    assert manifest.timeline_revision == 2
    assert manifest.items[0].source is not None
    assert manifest.items[0].source.sha256 == "a" * 64
    assert manifest.items[1].source is not None
    assert manifest.items[1].source.measured_duration_ms == 1_000
    assert manifest.captions[0].text == "తెలుగు"
    assert manifest.frame_count == 24


@pytest.mark.anyio
async def test_submit_rejects_unapproved_or_stale_timeline() -> None:
    fixtures = Fixtures(
        replace(_project(), approved_timeline_revision_id="other"),
        _timeline(),
    )

    with pytest.raises(DomainValidationError, match="approved timeline"):
        await _submit(fixtures)("project", "timeline", idempotency_key="stale")


@pytest.mark.anyio
async def test_submit_rejects_short_or_uninspected_audio() -> None:
    fixtures = Fixtures(_project(), _timeline())
    fixtures.assets["audio"] = replace(
        fixtures.assets["audio"],
        state=AssetState.READY,
        metadata=None,
        inspector_revision=None,
        inspected_at=None,
    )

    with pytest.raises(DomainValidationError, match="must be inspected"):
        await _submit(fixtures)("project", "timeline", idempotency_key="bad-audio")
