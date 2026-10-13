from __future__ import annotations

from datetime import datetime, timezone
from typing import cast

import pytest

from video_app.application.assets import AssetRepository
from video_app.application.films import (
    ApproveFilmSubject,
    FilmIdentifierFactory,
    FilmRepository,
    FilmWorkspace,
)
from video_app.application.ports import Clock
from video_app.application.projects import ProjectRepository
from video_app.domain.assets import (
    AssetKind,
    AssetState,
    MediaAsset,
    MediaMetadata,
    RightsDeclaration,
)
from video_app.domain.films import ApprovalStage, FilmApproval, film_workspace_fingerprint
from video_app.domain.models import DomainValidationError
from video_app.domain.projects import (
    AspectRatio,
    BudgetPolicy,
    ExportSettings,
    Project,
    ProjectDraft,
    ProjectMode,
    ProjectPreset,
    ProviderSelections,
)

NOW = datetime(2026, 10, 13, tzinfo=timezone.utc)


def _project() -> Project:
    return Project.create(
        project_id="project",
        owner_id="owner",
        draft=ProjectDraft(
            title="House to temple",
            language="te",
            mode=ProjectMode.LONG,
            target_duration_ms=900_000,
            aspect_ratio=AspectRatio.LANDSCAPE,
            export_settings=ExportSettings(1280, 720, 24),
            providers=ProviderSelections("wan22", speech="uploaded"),
            budget_policy=BudgetPolicy(),
            preset=ProjectPreset.TELUGU_SHORT_FILM_900,
        ),
        now=NOW,
    )


def _asset(*, duration_ms: int, with_audio: bool) -> MediaAsset:
    metadata = MediaMetadata(
        "mp4",
        duration_ms,
        width=1280,
        height=720,
        frame_rate_numerator=24,
        frame_rate_denominator=1,
        sample_rate=48_000 if with_audio else None,
        channels=2 if with_audio else None,
        sample_count=duration_ms * 48 if with_audio else None,
    )
    return MediaAsset(
        id="final_mix",
        project_id="project",
        owner_id="owner",
        version=2,
        kind=AssetKind.VIDEO,
        state=AssetState.INSPECTED,
        original_filename="final.mp4",
        media_type="video/mp4",
        storage_key="media/final.mp4",
        size_bytes=100,
        sha256="d" * 64,
        rights=RightsDeclaration.OWNED,
        created_at=NOW,
        metadata=metadata,
        inspector_revision="ffprobe-pinned",
        inspected_at=NOW,
    )


class Fixtures:
    def __init__(self, asset: MediaAsset) -> None:
        self.project = _project()
        workspace_fingerprint = film_workspace_fingerprint(
            (), (), self.project.film_contract_fingerprint()
        )
        self.workspace = FilmWorkspace(
            (),
            (),
            (
                FilmApproval(
                    "film-approval",
                    "project",
                    "owner",
                    ApprovalStage.FILM_900_SECONDS,
                    workspace_fingerprint,
                    NOW,
                    evidence_asset_id="film",
                ),
            ),
        )
        self.asset = asset
        self.saved: list[FilmApproval] = []

    async def get(self, owner_id: str, project_id: str, asset_id: str | None = None) -> object:
        assert owner_id == "owner" and project_id == "project"
        return self.project if asset_id is None else self.asset

    async def snapshot(self, owner_id: str, project_id: str) -> FilmWorkspace:
        assert owner_id == "owner" and project_id == "project"
        return self.workspace

    async def add_approval(self, approval: FilmApproval) -> FilmApproval:
        self.saved.append(approval)
        return approval


class FixedClock:
    def now(self) -> datetime:
        return NOW


class Identifiers:
    def new_scene_id(self) -> str:
        return "scene"

    def new_shot_id(self) -> str:
        return "shot"

    def new_approval_id(self) -> str:
        return "final-sound-approval"


def _approve(fixtures: Fixtures) -> ApproveFilmSubject:
    return ApproveFilmSubject(
        cast(ProjectRepository, fixtures),
        cast(AssetRepository, fixtures),
        cast(FilmRepository, fixtures),
        cast(Clock, FixedClock()),
        cast(FilmIdentifierFactory, Identifiers()),
        "owner",
    )


@pytest.mark.anyio
async def test_final_sound_requires_inspected_audio_for_the_complete_target() -> None:
    no_audio = Fixtures(_asset(duration_ms=900_000, with_audio=False))
    with pytest.raises(DomainValidationError, match="audio-bearing"):
        await _approve(no_audio)(
            "project",
            stage=ApprovalStage.FINAL_SOUND_MIX,
            scene_id=None,
            shot_id=None,
            evidence_asset_id="final_mix",
        )

    too_short = Fixtures(_asset(duration_ms=899_999, with_audio=True))
    with pytest.raises(DomainValidationError, match="cover the target"):
        await _approve(too_short)(
            "project",
            stage=ApprovalStage.FINAL_SOUND_MIX,
            scene_id=None,
            shot_id=None,
            evidence_asset_id="final_mix",
        )

    complete = Fixtures(_asset(duration_ms=900_000, with_audio=True))
    approval = await _approve(complete)(
        "project",
        stage=ApprovalStage.FINAL_SOUND_MIX,
        scene_id=None,
        shot_id=None,
        evidence_asset_id="final_mix",
    )
    assert approval.stage is ApprovalStage.FINAL_SOUND_MIX
    assert complete.saved == [approval]
