from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast

import pytest

from video_app.application.assets import AssetContentStore, AssetRepository
from video_app.application.films import FilmRepository
from video_app.application.library import (
    ApproveReferenceVideoGuidance,
    CreateReferenceVideoGuidance,
    FilmBibleRepository,
    GetReferenceVideoPreview,
    LibraryRepository,
    LibraryRevisionConflictError,
    ReferenceVideoGuidanceDraft,
    ReferenceVideoSelection,
)
from video_app.application.projects import ProjectRepository
from video_app.domain.assets import (
    AssetKind,
    AssetScope,
    AssetState,
    MediaAsset,
    MediaMetadata,
    RightsDeclaration,
)
from video_app.domain.films import DialogueWorkflow, FilmShot, FilmShotDraft, ReferenceWorkflow
from video_app.domain.library import (
    FilmBiblePin,
    FilmBiblePinRole,
    LibraryAssetBinding,
    LibraryEntity,
    LibraryEntityKind,
    LibraryVersion,
    LibraryVersionKind,
    ReferenceGuidanceStatus,
    ReferenceRole,
    ReferenceVideoGuidance,
    ReferenceVideoPurpose,
    ReferenceVideoSourceSnapshot,
    ShotBindingRevision,
)
from video_app.domain.models import DomainValidationError
from video_app.domain.projects import Project

NOW = datetime(2026, 10, 13, tzinfo=timezone.utc)


class Clock:
    def now(self) -> datetime:
        return NOW + timedelta(minutes=1)


class Identifiers:
    def __init__(self) -> None:
        self.value = 0

    def new_reference_video_guidance_id(self) -> str:
        self.value += 1
        return f"guidance_{self.value}"

    def new_starting_frame_composition_id(self) -> str:
        self.value += 1
        return f"composition_{self.value}"


class Projects:
    async def get(self, owner_id: str, project_id: str) -> Project:
        if (owner_id, project_id) != ("owner_a", "project_one"):
            raise LookupError(project_id)
        return cast(Project, object())


class Films:
    def __init__(self, shot: FilmShot) -> None:
        self.shot = shot

    async def get_shot(self, owner_id: str, project_id: str, shot_id: str) -> FilmShot:
        if (owner_id, project_id, shot_id) != (
            self.shot.owner_id,
            self.shot.project_id,
            self.shot.id,
        ):
            raise LookupError(shot_id)
        return self.shot


class Assets:
    def __init__(self, asset: MediaAsset) -> None:
        self.asset = asset

    async def get_owner(self, owner_id: str, asset_id: str) -> MediaAsset:
        if owner_id != self.asset.owner_id or asset_id != self.asset.id:
            raise LookupError(asset_id)
        return self.asset


class Library:
    async def get_version(self, owner_id: str, entity_id: str, version_id: str) -> LibraryVersion:
        raise LookupError(version_id)


class VersionLibrary:
    def __init__(self, version: LibraryVersion) -> None:
        self.version = version

    async def get_version(self, owner_id: str, entity_id: str, version_id: str) -> LibraryVersion:
        if (
            owner_id != self.version.owner_id
            or entity_id != self.version.entity_id
            or version_id != self.version.id
        ):
            raise LookupError(version_id)
        return self.version


class GuidanceRepository:
    def __init__(self, binding: ShotBindingRevision) -> None:
        self.binding = binding
        self.items: list[ReferenceVideoGuidance] = []

    async def get_shot_binding_revision(
        self, owner_id: str, project_id: str, shot_id: str, revision_id: str
    ) -> ShotBindingRevision:
        if revision_id != self.binding.id:
            raise LookupError(revision_id)
        return self.binding

    async def next_reference_guidance_revision(
        self, owner_id: str, project_id: str, shot_id: str
    ) -> int:
        return 1 + len(self.items)

    async def create_reference_video_guidance(
        self, guidance: ReferenceVideoGuidance
    ) -> ReferenceVideoGuidance:
        self.items.append(guidance)
        return guidance

    async def get_reference_video_guidance(
        self, owner_id: str, project_id: str, shot_id: str, guidance_id: str
    ) -> ReferenceVideoGuidance:
        return next(item for item in self.items if item.id == guidance_id)

    async def approve_reference_video_guidance(
        self, guidance: ReferenceVideoGuidance
    ) -> ReferenceVideoGuidance:
        self.items = [guidance if item.id == guidance.id else item for item in self.items]
        return guidance


class Content:
    def resolve_for_read(self, storage_key: str) -> Path:
        return Path("C:/safe") / storage_key


def _shot() -> FilmShot:
    draft = FilmShotDraft(
        position=0,
        target_duration_ms=5_000,
        description="A measured reference shot",
        reference_workflow=ReferenceWorkflow.REFERENCE_GENERATION,
        character_reference_asset_ids=("identity_one",),
        storyboard_asset_id="storyboard_one",
        dialogue_workflow=DialogueWorkflow.TTS,
    )
    return FilmShot(
        id="shot_one",
        scene_id="scene_one",
        project_id="project_one",
        owner_id="owner_a",
        version=1,
        draft=draft,
        content_fingerprint=draft.fingerprint(),
        created_at=NOW,
        updated_at=NOW,
    )


def _binding(shot: FilmShot) -> ShotBindingRevision:
    return ShotBindingRevision.create(
        binding_revision_id="binding_one",
        project_id=shot.project_id,
        owner_id=shot.owner_id,
        shot_id=shot.id,
        shot_version=shot.version,
        revision=1,
        film_bible_snapshot_id="bible_one",
        bindings=(
            FilmBiblePin(
                entity_id="character_one",
                library_version_id="version_one",
                library_version_number=1,
                version_kind=LibraryVersionKind.IDENTITY,
                version_fingerprint="a" * 64,
                role=FilmBiblePinRole.CHARACTER_IDENTITY,
            ),
        ),
        now=NOW,
    )


def _video(*, version: int = 2) -> MediaAsset:
    return MediaAsset(
        id="video_one",
        project_id="project_one",
        owner_id="owner_a",
        version=version,
        kind=AssetKind.VIDEO,
        state=AssetState.INSPECTED,
        original_filename="performance.mp4",
        media_type="video/mp4",
        storage_key="uploads/video-one.mp4",
        size_bytes=1000,
        sha256="b" * 64,
        rights=RightsDeclaration.PERMISSIONED,
        created_at=NOW,
        metadata=MediaMetadata(
            format_name="mov,mp4",
            duration_ms=12_000,
            width=1280,
            height=720,
            frame_rate_numerator=24,
            frame_rate_denominator=1,
        ),
        inspector_revision="ffprobe:test",
        inspected_at=NOW + timedelta(seconds=1),
        scope=AssetScope.PROJECT,
    )


def _source() -> ReferenceVideoSourceSnapshot:
    asset = _video()
    assert asset.metadata is not None
    return ReferenceVideoSourceSnapshot(
        asset_id=asset.id,
        asset_version=asset.version,
        asset_sha256=asset.sha256,
        media_type=asset.media_type,
        scope=asset.scope,
        inspector_revision=asset.inspector_revision or "",
        duration_ms=asset.metadata.duration_ms,
        width=asset.metadata.width or 0,
        height=asset.metadata.height or 0,
        frame_rate_numerator=asset.metadata.frame_rate_numerator or 0,
        frame_rate_denominator=asset.metadata.frame_rate_denominator or 0,
    )


def _library_video() -> MediaAsset:
    project_video = _video()
    return MediaAsset(
        id=project_video.id,
        project_id=None,
        owner_id=project_video.owner_id,
        version=project_video.version,
        kind=project_video.kind,
        state=project_video.state,
        original_filename=project_video.original_filename,
        media_type=project_video.media_type,
        storage_key=project_video.storage_key,
        size_bytes=project_video.size_bytes,
        sha256=project_video.sha256,
        rights=project_video.rights,
        created_at=project_video.created_at,
        metadata=project_video.metadata,
        inspector_revision=project_video.inspector_revision,
        inspected_at=project_video.inspected_at,
        scope=AssetScope.LIBRARY,
    )


def test_reference_guidance_rejects_unbounded_trim() -> None:
    with pytest.raises(DomainValidationError, match="between 250 and 30000"):
        ReferenceVideoGuidance.create(
            guidance_id="guidance_one",
            project_id="project_one",
            owner_id="owner_a",
            shot_id="shot_one",
            shot_version=1,
            shot_binding_revision_id="binding_one",
            revision=1,
            purpose=ReferenceVideoPurpose.MOTION_PERFORMANCE,
            source=_source(),
            trim_start_ms=0,
            trim_end_ms=100,
            guidance_notes="",
            now=NOW,
        )


@pytest.mark.anyio
async def test_new_trim_revision_preserves_approved_previous_guidance() -> None:
    shot = _shot()
    repository = GuidanceRepository(_binding(shot))
    assets = Assets(_video())
    create = CreateReferenceVideoGuidance(
        cast(ProjectRepository, Projects()),
        cast(FilmRepository, Films(shot)),
        cast(LibraryRepository, Library()),
        cast(FilmBibleRepository, repository),
        cast(AssetRepository, assets),
        Clock(),
        Identifiers(),
        "owner_a",
    )

    first = await create(
        "project_one",
        shot.id,
        ReferenceVideoGuidanceDraft(
            shot_version=1,
            shot_binding_revision_id="binding_one",
            purpose=ReferenceVideoPurpose.MOTION_PERFORMANCE,
            source=ReferenceVideoSelection("video_one"),
            trim_start_ms=1_000,
            trim_end_ms=4_000,
            guidance_notes="Use the measured walk timing only.",
        ),
    )
    approved = await ApproveReferenceVideoGuidance(
        cast(ProjectRepository, Projects()),
        cast(FilmRepository, Films(shot)),
        cast(LibraryRepository, Library()),
        cast(FilmBibleRepository, repository),
        cast(AssetRepository, assets),
        Clock(),
        "owner_a",
    )("project_one", shot.id, first.id)
    second = await create(
        "project_one",
        shot.id,
        ReferenceVideoGuidanceDraft(
            shot_version=1,
            shot_binding_revision_id="binding_one",
            purpose=ReferenceVideoPurpose.MOTION_PERFORMANCE,
            source=ReferenceVideoSelection("video_one"),
            trim_start_ms=5_000,
            trim_end_ms=8_000,
            guidance_notes="Corrected range.",
        ),
    )

    assert approved.status is ReferenceGuidanceStatus.APPROVED
    assert approved.trim_start_ms == 1_000
    assert second.status is ReferenceGuidanceStatus.DRAFT
    assert second.revision == 2
    assert second.fingerprint != approved.fingerprint
    assert repository.items[0] == approved


@pytest.mark.anyio
async def test_preview_rejects_asset_metadata_version_drift() -> None:
    shot = _shot()
    repository = GuidanceRepository(_binding(shot))
    guidance = ReferenceVideoGuidance.create(
        guidance_id="guidance_one",
        project_id="project_one",
        owner_id="owner_a",
        shot_id=shot.id,
        shot_version=1,
        shot_binding_revision_id="binding_one",
        revision=1,
        purpose=ReferenceVideoPurpose.SHOT_GUIDANCE,
        source=_source(),
        trim_start_ms=0,
        trim_end_ms=1_000,
        guidance_notes="",
        now=NOW,
    )
    repository.items.append(guidance)
    stale_assets = Assets(_video(version=3))

    with pytest.raises(LibraryRevisionConflictError, match="no longer matches"):
        await GetReferenceVideoPreview(
            cast(ProjectRepository, Projects()),
            cast(FilmRepository, Films(shot)),
            cast(FilmBibleRepository, repository),
            cast(AssetRepository, stale_assets),
            cast(AssetContentStore, Content()),
            "owner_a",
        )("project_one", shot.id, guidance.id)


@pytest.mark.anyio
async def test_library_video_purpose_must_match_approved_binding_role() -> None:
    shot = _shot()
    asset = _library_video()
    entity = LibraryEntity.create(
        entity_id="shot_reference_one",
        owner_id="owner_a",
        kind=LibraryEntityKind.SHOT_REFERENCE,
        display_name="Walk reference",
        aliases=(),
        now=NOW,
    )
    version = LibraryVersion.create(
        version_id="version_reference_one",
        entity=entity,
        version_number=1,
        kind=LibraryVersionKind.SHOT_REFERENCE,
        label="Walk timing",
        notes="",
        invariants="",
        state_notes="",
        voice_profile_id=None,
        rights_statement="Permission recorded",
        bindings=(
            LibraryAssetBinding(
                asset_id=asset.id,
                asset_version=asset.version,
                asset_sha256=asset.sha256,
                role=ReferenceRole.SHOT_GUIDANCE,
                view_label=None,
            ),
        ),
        now=NOW,
    ).approve(now=NOW + timedelta(seconds=1))
    binding = ShotBindingRevision.create(
        binding_revision_id="binding_reference_one",
        project_id=shot.project_id,
        owner_id=shot.owner_id,
        shot_id=shot.id,
        shot_version=shot.version,
        revision=1,
        film_bible_snapshot_id="bible_one",
        bindings=(
            FilmBiblePin(
                entity_id=entity.id,
                library_version_id=version.id,
                library_version_number=1,
                version_kind=LibraryVersionKind.SHOT_REFERENCE,
                version_fingerprint=version.fingerprint,
                role=FilmBiblePinRole.SHOT_REFERENCE,
            ),
        ),
        now=NOW,
    )
    repository = GuidanceRepository(binding)
    create = CreateReferenceVideoGuidance(
        cast(ProjectRepository, Projects()),
        cast(FilmRepository, Films(shot)),
        cast(LibraryRepository, VersionLibrary(version)),
        cast(FilmBibleRepository, repository),
        cast(AssetRepository, Assets(asset)),
        Clock(),
        Identifiers(),
        "owner_a",
    )

    with pytest.raises(DomainValidationError, match="purpose must match"):
        await create(
            "project_one",
            shot.id,
            ReferenceVideoGuidanceDraft(
                shot_version=1,
                shot_binding_revision_id=binding.id,
                purpose=ReferenceVideoPurpose.MOTION_PERFORMANCE,
                source=ReferenceVideoSelection(asset.id, entity.id, version.id),
                trim_start_ms=0,
                trim_end_ms=1_000,
                guidance_notes="",
            ),
        )
