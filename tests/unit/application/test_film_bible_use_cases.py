from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import cast

import pytest

from video_app.application.assets import AssetRepository
from video_app.application.films import FilmRepository
from video_app.application.library import (
    ApproveFilmBibleSnapshot,
    CompositionAssetSelection,
    CreateFilmBibleSnapshot,
    CreateShotBindingRevision,
    CreateStartingFrameComposition,
    FilmBiblePinSelection,
    FilmBibleRepository,
    LibraryRepository,
    ResolveFilmBibleName,
    StartingFrameDraft,
    StartingFrameLayerDraft,
)
from video_app.application.projects import ProjectRepository
from video_app.domain.assets import (
    AssetKind,
    AssetScope,
    AssetState,
    MediaAsset,
    RightsDeclaration,
)
from video_app.domain.films import (
    DialogueWorkflow,
    FilmShot,
    FilmShotDraft,
    ReferenceWorkflow,
)
from video_app.domain.library import (
    CompositionFit,
    CompositionLayerRole,
    FilmBiblePinRole,
    FilmBibleSnapshot,
    FilmBibleStatus,
    LayerTransform,
    LibraryAssetBinding,
    LibraryEntity,
    LibraryEntityKind,
    LibraryVersion,
    LibraryVersionKind,
    NameResolutionStatus,
    ReferenceRole,
    ShotBindingRevision,
    StartingFrameComposition,
    StartingFrameMode,
)
from video_app.domain.models import DomainValidationError
from video_app.domain.projects import Project

NOW = datetime(2026, 10, 13, tzinfo=timezone.utc)


class Clock:
    def now(self) -> datetime:
        return NOW + timedelta(minutes=1)


class Identifiers:
    def __init__(self) -> None:
        self.bibles = 0
        self.bindings = 0
        self.compositions = 0

    def new_film_bible_snapshot_id(self) -> str:
        self.bibles += 1
        return f"bible_{self.bibles}"

    def new_shot_binding_revision_id(self) -> str:
        self.bindings += 1
        return f"binding_{self.bindings}"

    def new_starting_frame_composition_id(self) -> str:
        self.compositions += 1
        return f"composition_{self.compositions}"

    def new_reference_video_guidance_id(self) -> str:
        self.compositions += 1
        return f"guidance_{self.compositions}"


class Projects:
    async def get(self, owner_id: str, project_id: str) -> Project:
        if owner_id != "owner_a" or project_id != "project_one":
            raise LookupError(project_id)
        return cast(Project, object())


class Films:
    def __init__(self, shots: tuple[FilmShot, ...]) -> None:
        self.shots = {shot.id: shot for shot in shots}

    async def get_shot(self, owner_id: str, project_id: str, shot_id: str) -> FilmShot:
        shot = self.shots[shot_id]
        if shot.owner_id != owner_id or shot.project_id != project_id:
            raise LookupError(shot_id)
        return shot


class MemoryLibrary:
    def __init__(self, entity: LibraryEntity, versions: tuple[LibraryVersion, ...]) -> None:
        self.entity = entity
        self.versions = {version.id: version for version in versions}
        self.snapshots: list[FilmBibleSnapshot] = []
        self.bindings: list[ShotBindingRevision] = []
        self.compositions: list[StartingFrameComposition] = []

    async def get_entity(self, owner_id: str, entity_id: str) -> LibraryEntity:
        if self.entity.owner_id != owner_id or self.entity.id != entity_id:
            raise LookupError(entity_id)
        return self.entity

    async def get_version(self, owner_id: str, entity_id: str, version_id: str) -> LibraryVersion:
        await self.get_entity(owner_id, entity_id)
        return self.versions[version_id]

    async def list_entities(
        self, owner_id: str, *, kind: LibraryEntityKind | None, limit: int
    ) -> tuple[LibraryEntity, ...]:
        if owner_id != self.entity.owner_id or (kind is not None and kind is not self.entity.kind):
            return ()
        return (self.entity,)[:limit]

    async def next_film_bible_revision(self, owner_id: str, project_id: str) -> int:
        return len(self.snapshots) + 1

    async def create_film_bible_snapshot(self, snapshot: FilmBibleSnapshot) -> FilmBibleSnapshot:
        self.snapshots.append(snapshot)
        return snapshot

    async def get_film_bible_snapshot(
        self, owner_id: str, project_id: str, snapshot_id: str
    ) -> FilmBibleSnapshot:
        return next(
            item
            for item in self.snapshots
            if item.id == snapshot_id
            and item.owner_id == owner_id
            and item.project_id == project_id
        )

    async def approve_film_bible_snapshot(self, snapshot: FilmBibleSnapshot) -> FilmBibleSnapshot:
        self.snapshots = [snapshot if item.id == snapshot.id else item for item in self.snapshots]
        return snapshot

    async def next_shot_binding_revision(self, owner_id: str, project_id: str, shot_id: str) -> int:
        return 1 + sum(item.shot_id == shot_id for item in self.bindings)

    async def create_shot_binding_revision(
        self, revision: ShotBindingRevision
    ) -> ShotBindingRevision:
        self.bindings.append(revision)
        return revision

    async def get_shot_binding_revision(
        self, owner_id: str, project_id: str, shot_id: str, revision_id: str
    ) -> ShotBindingRevision:
        return next(
            item
            for item in self.bindings
            if item.owner_id == owner_id
            and item.project_id == project_id
            and item.shot_id == shot_id
            and item.id == revision_id
        )

    async def next_starting_frame_revision(
        self, owner_id: str, project_id: str, shot_id: str
    ) -> int:
        return 1 + sum(item.shot_id == shot_id for item in self.compositions)

    async def create_starting_frame_composition(
        self, composition: StartingFrameComposition
    ) -> StartingFrameComposition:
        self.compositions.append(composition)
        return composition


class Assets:
    def __init__(self, *items: MediaAsset) -> None:
        self.items = {item.id: item for item in items}

    async def get_owner(self, owner_id: str, asset_id: str) -> MediaAsset:
        item = self.items[asset_id]
        if item.owner_id != owner_id:
            raise LookupError(asset_id)
        return item


def _version(entity: LibraryEntity, version_id: str, number: int, checksum: str) -> LibraryVersion:
    return LibraryVersion.create(
        version_id=version_id,
        entity=entity,
        version_number=number,
        kind=LibraryVersionKind.IDENTITY,
        label=f"Identity {number}",
        notes="",
        invariants="Face and hair",
        state_notes="",
        voice_profile_id=None,
        rights_statement="Permission recorded",
        bindings=(
            LibraryAssetBinding(
                asset_id=f"asset_{number}",
                asset_version=1,
                asset_sha256=checksum * 64,
                role=ReferenceRole.IDENTITY_APPEARANCE,
                view_label="front",
            ),
        ),
        now=NOW,
    ).approve(now=NOW + timedelta(seconds=number))


def _shot(shot_id: str) -> FilmShot:
    draft = FilmShotDraft(
        position=0,
        target_duration_ms=5_000,
        description="Arjun enters",
        reference_workflow=ReferenceWorkflow.REFERENCE_GENERATION,
        character_reference_asset_ids=("asset_project_reference",),
        storyboard_asset_id="asset_storyboard",
        dialogue_workflow=DialogueWorkflow.TTS,
    )
    return FilmShot(
        id=shot_id,
        scene_id="scene_one",
        project_id="project_one",
        owner_id="owner_a",
        version=1,
        draft=draft,
        content_fingerprint=draft.fingerprint(),
        created_at=NOW,
        updated_at=NOW,
    )


def _library_image(asset_id: str, checksum: str) -> MediaAsset:
    return MediaAsset(
        id=asset_id,
        project_id=None,
        owner_id="owner_a",
        version=1,
        kind=AssetKind.IMAGE,
        state=AssetState.READY,
        original_filename=f"{asset_id}.png",
        media_type="image/png",
        storage_key=f"uploads/{checksum * 32}.png",
        size_bytes=100,
        sha256=checksum * 64,
        rights=RightsDeclaration.PERMISSIONED,
        created_at=NOW,
        scope=AssetScope.LIBRARY,
    )


@pytest.mark.anyio
async def test_new_version_does_not_change_snapshot_and_rename_still_resolves() -> None:
    entity = LibraryEntity.create(
        entity_id="library_arjun",
        owner_id="owner_a",
        kind=LibraryEntityKind.CHARACTER,
        display_name="Arjun",
        aliases=("అర్జున్",),
        now=NOW,
    )
    first = _version(entity, "version_one", 1, "a")
    second = _version(entity, "version_two", 2, "b")
    repository = MemoryLibrary(entity, (first, second))
    identifiers = Identifiers()
    projects = cast(ProjectRepository, Projects())
    library = cast(LibraryRepository, repository)
    film_bibles = cast(FilmBibleRepository, repository)
    create = CreateFilmBibleSnapshot(
        projects, library, film_bibles, Clock(), identifiers, "owner_a"
    )
    snapshot = await create(
        "project_one",
        (FilmBiblePinSelection(entity.id, first.id, FilmBiblePinRole.CHARACTER_IDENTITY),),
    )
    approved = await ApproveFilmBibleSnapshot(projects, film_bibles, Clock(), "owner_a")(
        "project_one", snapshot.id
    )
    repository.entity = entity.rename(
        display_name="Arjun Rao",
        aliases=("అర్జున్", "Arjun"),
        expected_version=1,
        now=NOW + timedelta(minutes=2),
    )

    resolution = await ResolveFilmBibleName(projects, library, film_bibles, "owner_a")(
        "project_one", approved.id, "@అర్జున్"
    )

    assert approved.status is FilmBibleStatus.APPROVED
    assert approved.pins[0].library_version_id == first.id
    assert approved.pins[0].version_fingerprint == first.fingerprint
    assert resolution.status is NameResolutionStatus.RESOLVED
    assert resolution.candidates[0].entity_id == entity.id


@pytest.mark.anyio
async def test_rebinding_one_shot_preserves_unrelated_shot_revision() -> None:
    entity = LibraryEntity.create(
        entity_id="library_arjun",
        owner_id="owner_a",
        kind=LibraryEntityKind.CHARACTER,
        display_name="Arjun",
        aliases=(),
        now=NOW,
    )
    first = _version(entity, "version_one", 1, "a")
    second = _version(entity, "version_two", 2, "b")
    repository = MemoryLibrary(entity, (first, second))
    identifiers = Identifiers()
    projects = cast(ProjectRepository, Projects())
    library = cast(LibraryRepository, repository)
    film_bibles = cast(FilmBibleRepository, repository)
    create_snapshot = CreateFilmBibleSnapshot(
        projects, library, film_bibles, Clock(), identifiers, "owner_a"
    )
    old = await create_snapshot(
        "project_one",
        (FilmBiblePinSelection(entity.id, first.id, FilmBiblePinRole.CHARACTER_IDENTITY),),
    )
    old = await ApproveFilmBibleSnapshot(projects, film_bibles, Clock(), "owner_a")(
        "project_one", old.id
    )
    new = await create_snapshot(
        "project_one",
        (FilmBiblePinSelection(entity.id, second.id, FilmBiblePinRole.CHARACTER_IDENTITY),),
    )
    new = await ApproveFilmBibleSnapshot(projects, film_bibles, Clock(), "owner_a")(
        "project_one", new.id
    )
    shot_one, shot_two = _shot("shot_one"), _shot("shot_two")
    bind = CreateShotBindingRevision(
        projects,
        cast(FilmRepository, Films((shot_one, shot_two))),
        film_bibles,
        Clock(),
        identifiers,
        "owner_a",
    )
    await bind(
        "project_one",
        shot_one.id,
        shot_version=1,
        snapshot_id=old.id,
        selections=(
            FilmBiblePinSelection(entity.id, first.id, FilmBiblePinRole.CHARACTER_IDENTITY),
        ),
    )
    shot_two_binding = await bind(
        "project_one",
        shot_two.id,
        shot_version=1,
        snapshot_id=old.id,
        selections=(
            FilmBiblePinSelection(entity.id, first.id, FilmBiblePinRole.CHARACTER_IDENTITY),
        ),
    )
    await bind(
        "project_one",
        shot_one.id,
        shot_version=1,
        snapshot_id=new.id,
        selections=(
            FilmBiblePinSelection(entity.id, second.id, FilmBiblePinRole.CHARACTER_IDENTITY),
        ),
    )

    assert repository.bindings[-1].shot_id == shot_one.id
    assert repository.bindings[-1].bindings[0].library_version_id == second.id
    assert shot_two_binding.bindings[0].library_version_id == first.id
    assert shot_two_binding.revision == 1


@pytest.mark.anyio
async def test_starting_frame_pins_only_assets_from_exact_shot_binding() -> None:
    entity = LibraryEntity.create(
        entity_id="library_composed_frame",
        owner_id="owner_a",
        kind=LibraryEntityKind.SHOT_REFERENCE,
        display_name="Approved opening frame",
        aliases=(),
        now=NOW,
    )
    version = LibraryVersion.create(
        version_id="version_one",
        entity=entity,
        version_number=1,
        kind=LibraryVersionKind.SHOT_REFERENCE,
        label="Approved frame",
        notes="",
        invariants="",
        state_notes="",
        voice_profile_id=None,
        rights_statement="Permission recorded",
        bindings=(
            LibraryAssetBinding(
                asset_id="asset_frame",
                asset_version=1,
                asset_sha256="a" * 64,
                role=ReferenceRole.STARTING_FRAME,
                view_label=None,
            ),
        ),
        now=NOW,
    ).approve(now=NOW + timedelta(seconds=1))
    repository = MemoryLibrary(entity, (version,))
    identifiers = Identifiers()
    projects = cast(ProjectRepository, Projects())
    library = cast(LibraryRepository, repository)
    film_bibles = cast(FilmBibleRepository, repository)
    shot = _shot("shot_one")
    films = cast(FilmRepository, Films((shot,)))
    snapshot = await CreateFilmBibleSnapshot(
        projects, library, film_bibles, Clock(), identifiers, "owner_a"
    )(
        "project_one",
        (
            FilmBiblePinSelection(
                entity.id,
                version.id,
                FilmBiblePinRole.SHOT_REFERENCE,
            ),
        ),
    )
    snapshot = await ApproveFilmBibleSnapshot(projects, film_bibles, Clock(), "owner_a")(
        "project_one", snapshot.id
    )
    binding = await CreateShotBindingRevision(
        projects,
        films,
        film_bibles,
        Clock(),
        identifiers,
        "owner_a",
    )(
        "project_one",
        shot.id,
        shot_version=shot.version,
        snapshot_id=snapshot.id,
        selections=(
            FilmBiblePinSelection(
                entity.id,
                version.id,
                FilmBiblePinRole.SHOT_REFERENCE,
            ),
        ),
    )
    assets = cast(
        AssetRepository,
        Assets(_library_image("asset_frame", "a"), _library_image("asset_unbound", "b")),
    )
    create = CreateStartingFrameComposition(
        projects,
        films,
        library,
        film_bibles,
        assets,
        Clock(),
        identifiers,
        "owner_a",
    )

    def draft(asset_id: str) -> StartingFrameDraft:
        return StartingFrameDraft(
            shot_version=shot.version,
            shot_binding_revision_id=binding.id,
            mode=StartingFrameMode.COMPOSED_UPLOAD,
            canvas_width=832,
            canvas_height=480,
            background_rgba="#00000000",
            output_rights=RightsDeclaration.PERMISSIONED,
            framing_notes="Medium shot",
            pose_notes="Facing camera",
            action_notes="Walks forward",
            lighting_notes="Day exterior",
            visible_speaker_entity_id=None,
            layers=(
                StartingFrameLayerDraft(
                    role=CompositionLayerRole.STARTING_FRAME,
                    source=CompositionAssetSelection(
                        asset_id=asset_id,
                        library_entity_id=entity.id,
                        library_version_id=version.id,
                    ),
                    transform=LayerTransform(
                        x=0,
                        y=0,
                        width=832,
                        height=480,
                        rotation_millidegrees=0,
                        opacity_basis_points=10_000,
                        fit=CompositionFit.CONTAIN,
                    ),
                ),
            ),
        )

    composition = await create("project_one", shot.id, draft("asset_frame"))
    assert composition.layers[0].source.library_version_id == version.id
    assert composition.layers[0].source.asset_sha256 == "a" * 64
    with pytest.raises(DomainValidationError, match="exact asset"):
        await create("project_one", shot.id, draft("asset_unbound"))
