from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import cast

import pytest

from video_app.application.assets import AssetRepository
from video_app.application.films import FilmRepository, FilmWorkspace
from video_app.application.ports import Clock, IdentifierFactory, JobRepository
from video_app.application.projects import ProjectRepository
from video_app.application.rough_cuts import RoughCutProvider, SubmitRoughCut
from video_app.domain.assets import (
    AssetKind,
    AssetScope,
    AssetState,
    MediaAsset,
    MediaMetadata,
    RightsDeclaration,
)
from video_app.domain.films import (
    ApprovalStage,
    DialogueWorkflow,
    FilmApproval,
    FilmScene,
    FilmSceneDraft,
    FilmShot,
    FilmShotDraft,
    ReferenceWorkflow,
    SceneContinuity,
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
    ProjectPreset,
    ProviderSelections,
)

NOW = datetime(2026, 10, 13, tzinfo=timezone.utc)


class Fixtures:
    def __init__(
        self,
        project: Project,
        workspace: FilmWorkspace,
        assets: dict[str, MediaAsset],
    ) -> None:
        self.project = project
        self.workspace = workspace
        self.assets = assets
        self.enqueued: list[GenerationJob] = []

    async def get(self, owner_id: str, project_id: str, asset_id: str | None = None) -> object:
        assert owner_id == "owner"
        assert project_id == "project"
        return self.project if asset_id is None else self.assets[asset_id]

    async def snapshot(self, owner_id: str, project_id: str) -> FilmWorkspace:
        assert owner_id == "owner" and project_id == "project"
        return self.workspace

    async def enqueue(self, job: GenerationJob) -> GenerationJob:
        self.enqueued.append(job)
        return job


class FixedClock:
    def now(self) -> datetime:
        return NOW


class Identifiers:
    def new_job_id(self) -> str:
        return "job_rough_cut"

    def new_attempt_id(self) -> str:
        return "attempt"

    def new_lease_token(self) -> str:
        return "lease"

    def new_correlation_id(self) -> str:
        return "correlation"


def _project() -> Project:
    return Project.create(
        project_id="project",
        owner_id="owner",
        draft=ProjectDraft(
            title="Telugu film",
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


def _asset(asset_id: str, kind: AssetKind, *, inspected: bool = False) -> MediaAsset:
    metadata = MediaMetadata(
        "wav", 450_000, sample_rate=48_000, channels=2, sample_count=21_600_000
    )
    return MediaAsset(
        id=asset_id,
        project_id="project",
        owner_id="owner",
        version=2 if inspected else 1,
        kind=kind,
        state=AssetState.INSPECTED if inspected else AssetState.READY,
        original_filename=f"{asset_id}.{'wav' if kind is AssetKind.AUDIO else 'png'}",
        media_type="audio/wav" if kind is AssetKind.AUDIO else "image/png",
        storage_key=f"uploads/{asset_id}.{'wav' if kind is AssetKind.AUDIO else 'png'}",
        size_bytes=100,
        sha256=("a" if kind is AssetKind.IMAGE else "b") * 64,
        rights=RightsDeclaration.PERMISSIONED,
        created_at=NOW,
        metadata=metadata if inspected else None,
        inspector_revision="ffprobe-pinned" if inspected else None,
        inspected_at=NOW if inspected else None,
        scope=AssetScope.PROJECT,
    )


def _workspace(*, tts: bool = False) -> tuple[FilmWorkspace, dict[str, MediaAsset]]:
    scene_draft = FilmSceneDraft(
        0,
        "Complete film",
        900_000,
        "తెలుగు సంభాషణ",
        "Reviewed pronunciation",
        SceneContinuity("house", "day", "blue", "cup", "dry", "A left"),
    )
    scene = FilmScene(
        "scene", "project", "owner", 1, scene_draft, scene_draft.fingerprint(), NOW, NOW
    )
    shots: list[FilmShot] = []
    approvals: list[FilmApproval] = [
        FilmApproval(
            "script",
            "project",
            "owner",
            ApprovalStage.TELUGU_SCRIPT,
            scene.content_fingerprint,
            NOW,
            scene_id=scene.id,
        ),
        FilmApproval(
            "pronunciation",
            "project",
            "owner",
            ApprovalStage.PRONUNCIATION,
            scene.content_fingerprint,
            NOW,
            scene_id=scene.id,
        ),
    ]
    assets: dict[str, MediaAsset] = {}
    for position in range(2):
        image_id = f"storyboard_{position}"
        audio_id = f"dialogue_{position}"
        assets[image_id] = _asset(image_id, AssetKind.IMAGE)
        assets[audio_id] = _asset(audio_id, AssetKind.AUDIO, inspected=True)
        draft = FilmShotDraft(
            position,
            450_000,
            f"Shot {position}",
            ReferenceWorkflow.REFERENCE_GENERATION,
            (image_id,),
            image_id,
            DialogueWorkflow.TTS if tts else DialogueWorkflow.RECORDED,
            recorded_dialogue_asset_id=None if tts else audio_id,
        )
        shot = FilmShot(
            f"shot_{position}",
            scene.id,
            "project",
            "owner",
            1,
            draft,
            draft.fingerprint(),
            NOW,
            NOW,
        )
        shots.append(shot)
        approvals.extend(
            (
                FilmApproval(
                    f"storyboard_approval_{position}",
                    "project",
                    "owner",
                    ApprovalStage.STORYBOARD,
                    shot.content_fingerprint,
                    NOW,
                    scene_id=scene.id,
                    shot_id=shot.id,
                    evidence_asset_id=image_id,
                ),
                FilmApproval(
                    f"voice_approval_{position}",
                    "project",
                    "owner",
                    ApprovalStage.VOICE_PERFORMANCE,
                    shot.content_fingerprint,
                    NOW,
                    scene_id=scene.id,
                    shot_id=shot.id,
                    evidence_asset_id=audio_id,
                ),
            )
        )
    return FilmWorkspace((scene,), tuple(shots), tuple(approvals)), assets


def _submit(fixtures: Fixtures) -> SubmitRoughCut:
    return SubmitRoughCut(
        cast(ProjectRepository, fixtures),
        cast(FilmRepository, fixtures),
        cast(AssetRepository, fixtures),
        cast(JobRepository, fixtures),
        RoughCutProvider(
            "ffmpeg-rough-cut",
            "ffmpeg-rough-cut-v1",
            "Rough cut",
            True,
            "qualified",
            1280,
            720,
            24,
            1,
        ),
        cast(Clock, FixedClock()),
        cast(IdentifierFactory, Identifiers()),
        "owner",
    )


@pytest.mark.anyio
async def test_submit_freezes_current_approved_inputs_and_is_deterministic() -> None:
    workspace, assets = _workspace()
    fixtures = Fixtures(_project(), workspace, assets)

    job = await _submit(fixtures)("project", idempotency_key="rough-cut-v1")

    manifest = job.request.rough_cut
    assert job.request.mode is GenerationMode.ROUGH_CUT
    assert manifest is not None
    assert manifest.total_duration_ms == 900_000
    assert manifest.frame_count == 21_600
    assert tuple(item.shot_id for item in manifest.items) == ("shot_0", "shot_1")
    assert manifest.items[0].dialogue.asset_version == 2
    assert len(manifest.manifest_fingerprint) == 64


@pytest.mark.anyio
async def test_tts_shots_fail_without_qualified_audio_asset() -> None:
    workspace, assets = _workspace(tts=True)
    fixtures = Fixtures(_project(), workspace, assets)

    with pytest.raises(DomainValidationError, match="recorded dialogue"):
        await _submit(fixtures)("project", idempotency_key="rough-cut-tts")


@pytest.mark.anyio
async def test_replacing_one_shot_preserves_unrelated_approved_assets() -> None:
    workspace, assets = _workspace()
    first = await _submit(Fixtures(_project(), workspace, assets))(
        "project", idempotency_key="first"
    )
    changed = workspace.shots[0].revise(
        replace(workspace.shots[0].draft, description="Replacement"), now=NOW
    )
    revised_workspace = replace(workspace, shots=(changed, workspace.shots[1]))
    fixtures = Fixtures(_project(), revised_workspace, assets)

    with pytest.raises(DomainValidationError, match="storyboard"):
        await _submit(fixtures)("project", idempotency_key="second")

    assert first.request.rough_cut is not None
    assert first.request.rough_cut.items[1].storyboard.asset_id == "storyboard_1"
