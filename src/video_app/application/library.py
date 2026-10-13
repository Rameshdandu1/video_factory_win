"""Use cases and ports for the reusable owner-scoped film library."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from video_app.application.assets import (
    AssetContentStore,
    AssetIdentifierFactory,
    AssetRepository,
    StoredUpload,
)
from video_app.application.films import FilmRepository
from video_app.application.ports import Clock
from video_app.application.projects import ProjectRepository
from video_app.domain.assets import AssetKind, AssetScope, AssetState, MediaAsset, RightsDeclaration
from video_app.domain.library import (
    CompositionAssetSnapshot,
    CompositionLayerRole,
    FilmBibleNameResolution,
    FilmBiblePin,
    FilmBiblePinRole,
    FilmBibleSnapshot,
    FilmBibleStatus,
    LayerTransform,
    LibraryAssetBinding,
    LibraryEntity,
    LibraryEntityKind,
    LibraryMetadataVersionError,
    LibraryVersion,
    LibraryVersionKind,
    LibraryVersionStatus,
    ReferenceRole,
    ReferenceVideoGuidance,
    ReferenceVideoPurpose,
    ReferenceVideoSourceSnapshot,
    ShotBindingRevision,
    StartingFrameComposition,
    StartingFrameLayer,
    StartingFrameMode,
    StartingFrameStatus,
    normalize_display_text,
    resolve_film_bible_name,
)
from video_app.domain.models import DomainValidationError


class LibraryEntityNotFoundError(LookupError):
    """Raised when a library entity is absent or outside the owner boundary."""


class LibraryVersionNotFoundError(LookupError):
    """Raised when a library version is absent or outside the owner boundary."""


class LibraryRevisionConflictError(RuntimeError):
    """Raised when optimistic concurrency rejects a library operation."""


class FilmBibleSnapshotNotFoundError(LookupError):
    """Raised when a Film Bible snapshot is absent or outside its project/owner."""


class ShotBindingRevisionNotFoundError(LookupError):
    """Raised when a shot has no requested binding revision."""


class StartingFrameCompositionNotFoundError(LookupError):
    """Raised when a starting-frame composition is outside its project/owner boundary."""


class StartingFrameRenderError(ValueError):
    """Raised when a pinned source cannot be rasterized safely."""


class ReferenceVideoGuidanceNotFoundError(LookupError):
    """Raised when reference guidance is absent or outside its owner/project/shot boundary."""


class LibraryIdentifierFactory(Protocol):
    def new_library_entity_id(self) -> str: ...

    def new_library_version_id(self) -> str: ...


class FilmBibleIdentifierFactory(Protocol):
    def new_film_bible_snapshot_id(self) -> str: ...

    def new_shot_binding_revision_id(self) -> str: ...


class StartingFrameIdentifierFactory(Protocol):
    def new_starting_frame_composition_id(self) -> str: ...

    def new_reference_video_guidance_id(self) -> str: ...


class StartingFrameContentStore(Protocol):
    async def store_generated_image(
        self, *, filename: str, candidate_path: Path
    ) -> StoredUpload: ...

    async def delete(self, storage_key: str) -> None: ...

    def resolve_for_read(self, storage_key: str) -> Path: ...


class LibraryRepository(Protocol):
    async def create_entity(self, entity: LibraryEntity) -> LibraryEntity: ...

    async def get_entity(self, owner_id: str, entity_id: str) -> LibraryEntity: ...

    async def list_entities(
        self, owner_id: str, *, kind: LibraryEntityKind | None, limit: int
    ) -> tuple[LibraryEntity, ...]: ...

    async def update_entity(
        self, entity: LibraryEntity, *, expected_version: int
    ) -> LibraryEntity: ...

    async def next_version_number(self, owner_id: str, entity_id: str) -> int: ...

    async def create_version(self, version: LibraryVersion) -> LibraryVersion: ...

    async def get_version(
        self, owner_id: str, entity_id: str, version_id: str
    ) -> LibraryVersion: ...

    async def list_versions(
        self, owner_id: str, entity_id: str, *, limit: int
    ) -> tuple[LibraryVersion, ...]: ...

    async def approve_version(self, version: LibraryVersion) -> LibraryVersion: ...


class FilmBibleRepository(Protocol):
    async def next_film_bible_revision(self, owner_id: str, project_id: str) -> int: ...

    async def create_film_bible_snapshot(
        self, snapshot: FilmBibleSnapshot
    ) -> FilmBibleSnapshot: ...

    async def get_film_bible_snapshot(
        self, owner_id: str, project_id: str, snapshot_id: str
    ) -> FilmBibleSnapshot: ...

    async def list_film_bible_snapshots(
        self, owner_id: str, project_id: str, *, limit: int
    ) -> tuple[FilmBibleSnapshot, ...]: ...

    async def approve_film_bible_snapshot(
        self, snapshot: FilmBibleSnapshot
    ) -> FilmBibleSnapshot: ...

    async def next_shot_binding_revision(
        self, owner_id: str, project_id: str, shot_id: str
    ) -> int: ...

    async def create_shot_binding_revision(
        self, revision: ShotBindingRevision
    ) -> ShotBindingRevision: ...

    async def list_shot_binding_revisions(
        self, owner_id: str, project_id: str, shot_id: str, *, limit: int
    ) -> tuple[ShotBindingRevision, ...]: ...

    async def get_shot_binding_revision(
        self, owner_id: str, project_id: str, shot_id: str, revision_id: str
    ) -> ShotBindingRevision: ...

    async def next_starting_frame_revision(
        self, owner_id: str, project_id: str, shot_id: str
    ) -> int: ...

    async def create_starting_frame_composition(
        self, composition: StartingFrameComposition
    ) -> StartingFrameComposition: ...

    async def get_starting_frame_composition(
        self, owner_id: str, project_id: str, shot_id: str, composition_id: str
    ) -> StartingFrameComposition: ...

    async def list_starting_frame_compositions(
        self, owner_id: str, project_id: str, shot_id: str, *, limit: int
    ) -> tuple[StartingFrameComposition, ...]: ...

    async def publish_starting_frame_render(
        self, composition: StartingFrameComposition, asset: MediaAsset
    ) -> StartingFrameComposition: ...

    async def approve_starting_frame_composition(
        self, composition: StartingFrameComposition
    ) -> StartingFrameComposition: ...

    async def next_reference_guidance_revision(
        self, owner_id: str, project_id: str, shot_id: str
    ) -> int: ...

    async def create_reference_video_guidance(
        self, guidance: ReferenceVideoGuidance
    ) -> ReferenceVideoGuidance: ...

    async def get_reference_video_guidance(
        self, owner_id: str, project_id: str, shot_id: str, guidance_id: str
    ) -> ReferenceVideoGuidance: ...

    async def list_reference_video_guidance(
        self, owner_id: str, project_id: str, shot_id: str, *, limit: int
    ) -> tuple[ReferenceVideoGuidance, ...]: ...

    async def approve_reference_video_guidance(
        self, guidance: ReferenceVideoGuidance
    ) -> ReferenceVideoGuidance: ...

    async def affected_shot_ids(
        self,
        owner_id: str,
        project_id: str,
        entity_id: str,
        version_id: str,
    ) -> tuple[str, ...]: ...


@dataclass(frozen=True, slots=True)
class LibraryAssetSelection:
    asset_id: str
    role: ReferenceRole
    view_label: str | None = None


@dataclass(frozen=True, slots=True)
class LibraryVersionDraft:
    kind: LibraryVersionKind
    label: str
    notes: str
    invariants: str
    state_notes: str
    voice_profile_id: str | None
    rights_statement: str
    assets: tuple[LibraryAssetSelection, ...]


@dataclass(frozen=True, slots=True)
class FilmBiblePinSelection:
    entity_id: str
    version_id: str
    role: FilmBiblePinRole


@dataclass(frozen=True, slots=True)
class CompositionAssetSelection:
    asset_id: str
    library_entity_id: str | None = None
    library_version_id: str | None = None


@dataclass(frozen=True, slots=True)
class ReferenceVideoSelection:
    asset_id: str
    library_entity_id: str | None = None
    library_version_id: str | None = None


@dataclass(frozen=True, slots=True)
class ReferenceVideoGuidanceDraft:
    shot_version: int
    shot_binding_revision_id: str
    purpose: ReferenceVideoPurpose
    source: ReferenceVideoSelection
    trim_start_ms: int
    trim_end_ms: int
    guidance_notes: str


@dataclass(frozen=True, slots=True)
class StartingFrameLayerDraft:
    role: CompositionLayerRole
    source: CompositionAssetSelection
    transform: LayerTransform
    mask: CompositionAssetSelection | None = None


@dataclass(frozen=True, slots=True)
class StartingFrameDraft:
    shot_version: int
    shot_binding_revision_id: str
    mode: StartingFrameMode
    canvas_width: int
    canvas_height: int
    background_rgba: str
    output_rights: RightsDeclaration
    framing_notes: str
    pose_notes: str
    action_notes: str
    lighting_notes: str
    visible_speaker_entity_id: str | None
    layers: tuple[StartingFrameLayerDraft, ...]


class StartingFrameRenderer(Protocol):
    @property
    def revision(self) -> str: ...

    async def render(
        self,
        composition: StartingFrameComposition,
        source_paths: Mapping[str, Path],
    ) -> Path: ...

    async def discard_candidate(self, candidate_path: Path) -> None: ...


@dataclass(frozen=True, slots=True)
class CreateLibraryEntity:
    repository: LibraryRepository
    clock: Clock
    identifiers: LibraryIdentifierFactory
    owner_id: str

    async def __call__(
        self,
        *,
        kind: LibraryEntityKind,
        display_name: str,
        aliases: tuple[str, ...],
    ) -> LibraryEntity:
        entity = LibraryEntity.create(
            entity_id=self.identifiers.new_library_entity_id(),
            owner_id=self.owner_id,
            kind=kind,
            display_name=display_name,
            aliases=aliases,
            now=self.clock.now(),
        )
        return await self.repository.create_entity(entity)


@dataclass(frozen=True, slots=True)
class GetLibraryEntity:
    repository: LibraryRepository
    owner_id: str

    async def __call__(self, entity_id: str) -> LibraryEntity:
        return await self.repository.get_entity(self.owner_id, entity_id)


@dataclass(frozen=True, slots=True)
class ListLibraryEntities:
    repository: LibraryRepository
    owner_id: str

    async def __call__(
        self,
        *,
        kind: LibraryEntityKind | None = None,
        query: str | None = None,
        limit: int = 100,
    ) -> tuple[LibraryEntity, ...]:
        if not 1 <= limit <= 100:
            raise ValueError("library list limit must be between 1 and 100")
        items = await self.repository.list_entities(self.owner_id, kind=kind, limit=limit)
        if query is None or not query.strip():
            return items
        return tuple(item for item in items if item.matches(query))


@dataclass(frozen=True, slots=True)
class UpdateLibraryEntity:
    repository: LibraryRepository
    clock: Clock
    owner_id: str

    async def __call__(
        self,
        entity_id: str,
        *,
        display_name: str,
        aliases: tuple[str, ...],
        expected_version: int,
    ) -> LibraryEntity:
        current = await self.repository.get_entity(self.owner_id, entity_id)
        try:
            revised = current.rename(
                display_name=display_name,
                aliases=aliases,
                expected_version=expected_version,
                now=self.clock.now(),
            )
        except LibraryMetadataVersionError as error:
            raise LibraryRevisionConflictError(str(error)) from error
        return await self.repository.update_entity(revised, expected_version=expected_version)


def _validate_asset_role(kind: AssetKind, role: ReferenceRole) -> None:
    if role in {ReferenceRole.IDENTITY_APPEARANCE, ReferenceRole.STARTING_FRAME}:
        if kind is not AssetKind.IMAGE:
            raise DomainValidationError(f"{role.value} requires an image asset")
    elif role in {ReferenceRole.MOTION_PERFORMANCE, ReferenceRole.SHOT_GUIDANCE}:
        if kind is not AssetKind.VIDEO:
            raise DomainValidationError(f"{role.value} requires a video asset")
    elif role is ReferenceRole.LOCATION_OR_PROP and kind is AssetKind.AUDIO:
        raise DomainValidationError("location_or_prop references must be visual media")
    elif role is ReferenceRole.SOURCE_LAYER and kind is AssetKind.AUDIO:
        raise DomainValidationError("source layers must be visual media")


@dataclass(frozen=True, slots=True)
class CreateLibraryVersion:
    repository: LibraryRepository
    assets: AssetRepository
    clock: Clock
    identifiers: LibraryIdentifierFactory
    owner_id: str

    async def __call__(self, entity_id: str, draft: LibraryVersionDraft) -> LibraryVersion:
        entity = await self.repository.get_entity(self.owner_id, entity_id)
        if not draft.assets:
            raise DomainValidationError("library versions require at least one asset")
        bindings: list[LibraryAssetBinding] = []
        for selection in draft.assets:
            asset = await self.assets.get_owner(self.owner_id, selection.asset_id)
            if asset.scope is not AssetScope.LIBRARY:
                raise DomainValidationError("library versions may bind only library assets")
            _validate_asset_role(asset.kind, selection.role)
            bindings.append(
                LibraryAssetBinding(
                    asset_id=asset.id,
                    asset_version=asset.version,
                    asset_sha256=asset.sha256,
                    role=selection.role,
                    view_label=(
                        normalize_display_text(
                            selection.view_label, field="view label", maximum=100
                        )
                        if selection.view_label is not None
                        else None
                    ),
                )
            )
        version = LibraryVersion.create(
            version_id=self.identifiers.new_library_version_id(),
            entity=entity,
            version_number=await self.repository.next_version_number(self.owner_id, entity_id),
            kind=draft.kind,
            label=draft.label,
            notes=draft.notes,
            invariants=draft.invariants,
            state_notes=draft.state_notes,
            voice_profile_id=draft.voice_profile_id,
            rights_statement=draft.rights_statement,
            bindings=tuple(bindings),
            now=self.clock.now(),
        )
        return await self.repository.create_version(version)


@dataclass(frozen=True, slots=True)
class ListLibraryVersions:
    repository: LibraryRepository
    owner_id: str

    async def __call__(self, entity_id: str, *, limit: int = 100) -> tuple[LibraryVersion, ...]:
        if not 1 <= limit <= 100:
            raise ValueError("library version limit must be between 1 and 100")
        await self.repository.get_entity(self.owner_id, entity_id)
        return await self.repository.list_versions(self.owner_id, entity_id, limit=limit)


@dataclass(frozen=True, slots=True)
class ApproveLibraryVersion:
    repository: LibraryRepository
    clock: Clock
    owner_id: str

    async def __call__(self, entity_id: str, version_id: str) -> LibraryVersion:
        current = await self.repository.get_version(self.owner_id, entity_id, version_id)
        return await self.repository.approve_version(current.approve(now=self.clock.now()))


@dataclass(frozen=True, slots=True)
class CreateFilmBibleSnapshot:
    projects: ProjectRepository
    library: LibraryRepository
    film_bibles: FilmBibleRepository
    clock: Clock
    identifiers: FilmBibleIdentifierFactory
    owner_id: str

    async def __call__(
        self, project_id: str, selections: tuple[FilmBiblePinSelection, ...]
    ) -> FilmBibleSnapshot:
        await self.projects.get(self.owner_id, project_id)
        if not selections:
            raise DomainValidationError("film-bible snapshots require at least one pin")
        pins: list[FilmBiblePin] = []
        for selection in selections:
            entity = await self.library.get_entity(self.owner_id, selection.entity_id)
            version = await self.library.get_version(
                self.owner_id, selection.entity_id, selection.version_id
            )
            if version.status is not LibraryVersionStatus.APPROVED:
                raise DomainValidationError("film-bible pins require approved library versions")
            pin = FilmBiblePin(
                entity_id=entity.id,
                library_version_id=version.id,
                library_version_number=version.version_number,
                version_kind=version.kind,
                version_fingerprint=version.fingerprint,
                role=selection.role,
            )
            pins.append(pin)
        snapshot = FilmBibleSnapshot.create(
            snapshot_id=self.identifiers.new_film_bible_snapshot_id(),
            project_id=project_id,
            owner_id=self.owner_id,
            revision=await self.film_bibles.next_film_bible_revision(self.owner_id, project_id),
            pins=tuple(pins),
            now=self.clock.now(),
        )
        return await self.film_bibles.create_film_bible_snapshot(snapshot)


@dataclass(frozen=True, slots=True)
class ListFilmBibleSnapshots:
    projects: ProjectRepository
    film_bibles: FilmBibleRepository
    owner_id: str

    async def __call__(self, project_id: str, *, limit: int = 100) -> tuple[FilmBibleSnapshot, ...]:
        if not 1 <= limit <= 100:
            raise ValueError("film-bible snapshot limit must be between 1 and 100")
        await self.projects.get(self.owner_id, project_id)
        return await self.film_bibles.list_film_bible_snapshots(
            self.owner_id, project_id, limit=limit
        )


@dataclass(frozen=True, slots=True)
class ApproveFilmBibleSnapshot:
    projects: ProjectRepository
    film_bibles: FilmBibleRepository
    clock: Clock
    owner_id: str

    async def __call__(self, project_id: str, snapshot_id: str) -> FilmBibleSnapshot:
        await self.projects.get(self.owner_id, project_id)
        current = await self.film_bibles.get_film_bible_snapshot(
            self.owner_id, project_id, snapshot_id
        )
        return await self.film_bibles.approve_film_bible_snapshot(
            current.approve(now=self.clock.now())
        )


@dataclass(frozen=True, slots=True)
class ResolveFilmBibleName:
    projects: ProjectRepository
    library: LibraryRepository
    film_bibles: FilmBibleRepository
    owner_id: str

    async def __call__(
        self,
        project_id: str,
        snapshot_id: str,
        mention: str,
        *,
        kind: LibraryEntityKind | None = None,
    ) -> FilmBibleNameResolution:
        await self.projects.get(self.owner_id, project_id)
        snapshot = await self.film_bibles.get_film_bible_snapshot(
            self.owner_id, project_id, snapshot_id
        )
        if snapshot.status is not FilmBibleStatus.APPROVED:
            raise DomainValidationError("name resolution requires an approved Film Bible")
        entities = await self.library.list_entities(self.owner_id, kind=kind, limit=10_000)
        return resolve_film_bible_name(snapshot, entities, mention, kind=kind)


@dataclass(frozen=True, slots=True)
class CreateShotBindingRevision:
    projects: ProjectRepository
    films: FilmRepository
    film_bibles: FilmBibleRepository
    clock: Clock
    identifiers: FilmBibleIdentifierFactory
    owner_id: str

    async def __call__(
        self,
        project_id: str,
        shot_id: str,
        *,
        shot_version: int,
        snapshot_id: str,
        selections: tuple[FilmBiblePinSelection, ...],
    ) -> ShotBindingRevision:
        await self.projects.get(self.owner_id, project_id)
        shot = await self.films.get_shot(self.owner_id, project_id, shot_id)
        if shot.version != shot_version:
            raise LibraryRevisionConflictError("the shot changed before references were bound")
        snapshot = await self.film_bibles.get_film_bible_snapshot(
            self.owner_id, project_id, snapshot_id
        )
        if snapshot.status is not FilmBibleStatus.APPROVED:
            raise DomainValidationError("shot bindings require an approved Film Bible")
        selected: list[FilmBiblePin] = []
        for selection in selections:
            match = next(
                (
                    pin
                    for pin in snapshot.pins
                    if pin.entity_id == selection.entity_id
                    and pin.library_version_id == selection.version_id
                    and pin.role is selection.role
                ),
                None,
            )
            if match is None:
                raise DomainValidationError("shot bindings must use exact Film Bible pins")
            selected.append(match)
        revision = ShotBindingRevision.create(
            binding_revision_id=self.identifiers.new_shot_binding_revision_id(),
            project_id=project_id,
            owner_id=self.owner_id,
            shot_id=shot_id,
            shot_version=shot_version,
            revision=await self.film_bibles.next_shot_binding_revision(
                self.owner_id, project_id, shot_id
            ),
            film_bible_snapshot_id=snapshot_id,
            bindings=tuple(selected),
            now=self.clock.now(),
        )
        return await self.film_bibles.create_shot_binding_revision(revision)


@dataclass(frozen=True, slots=True)
class ListShotBindingRevisions:
    projects: ProjectRepository
    films: FilmRepository
    film_bibles: FilmBibleRepository
    owner_id: str

    async def __call__(
        self, project_id: str, shot_id: str, *, limit: int = 100
    ) -> tuple[ShotBindingRevision, ...]:
        if not 1 <= limit <= 100:
            raise ValueError("shot-binding revision limit must be between 1 and 100")
        await self.projects.get(self.owner_id, project_id)
        await self.films.get_shot(self.owner_id, project_id, shot_id)
        return await self.film_bibles.list_shot_binding_revisions(
            self.owner_id, project_id, shot_id, limit=limit
        )


@dataclass(frozen=True, slots=True)
class ListAffectedShots:
    projects: ProjectRepository
    library: LibraryRepository
    film_bibles: FilmBibleRepository
    owner_id: str

    async def __call__(self, project_id: str, entity_id: str, version_id: str) -> tuple[str, ...]:
        await self.projects.get(self.owner_id, project_id)
        await self.library.get_version(self.owner_id, entity_id, version_id)
        return await self.film_bibles.affected_shot_ids(
            self.owner_id, project_id, entity_id, version_id
        )


async def _composition_asset_snapshot(
    *,
    selection: CompositionAssetSelection,
    project_id: str,
    binding_revision: ShotBindingRevision,
    assets: AssetRepository,
    library: LibraryRepository,
    owner_id: str,
) -> tuple[CompositionAssetSnapshot, ReferenceRole | None]:
    asset = await assets.get_owner(owner_id, selection.asset_id)
    if asset.kind is not AssetKind.IMAGE:
        raise DomainValidationError("starting-frame sources and masks must be image assets")
    if asset.scope is AssetScope.PROJECT:
        if asset.project_id != project_id:
            raise DomainValidationError("project composition assets must belong to this project")
        if selection.library_entity_id is not None or selection.library_version_id is not None:
            raise DomainValidationError("project assets cannot claim library provenance")
        return (
            CompositionAssetSnapshot(
                asset_id=asset.id,
                asset_version=asset.version,
                asset_sha256=asset.sha256,
                scope=asset.scope,
            ),
            None,
        )
    if selection.library_entity_id is None or selection.library_version_id is None:
        raise DomainValidationError("library sources require an exact entity and version selection")
    pin = next(
        (
            candidate
            for candidate in binding_revision.bindings
            if candidate.entity_id == selection.library_entity_id
            and candidate.library_version_id == selection.library_version_id
        ),
        None,
    )
    if pin is None:
        raise DomainValidationError("library source is not pinned by this shot-binding revision")
    version = await library.get_version(
        owner_id, selection.library_entity_id, selection.library_version_id
    )
    if version.status is not LibraryVersionStatus.APPROVED:
        raise DomainValidationError("composition library sources require approved versions")
    if version.fingerprint != pin.version_fingerprint:
        raise DomainValidationError("the selected library version no longer matches its shot pin")
    exact_binding = next(
        (candidate for candidate in version.bindings if candidate.asset_id == asset.id), None
    )
    if (
        exact_binding is None
        or exact_binding.asset_version != asset.version
        or exact_binding.asset_sha256 != asset.sha256
    ):
        raise DomainValidationError("library source is not an exact asset in the selected version")
    if exact_binding.role not in {
        ReferenceRole.IDENTITY_APPEARANCE,
        ReferenceRole.LOCATION_OR_PROP,
        ReferenceRole.SOURCE_LAYER,
        ReferenceRole.STARTING_FRAME,
    }:
        raise DomainValidationError("the selected library asset is not approved as a source layer")
    return (
        CompositionAssetSnapshot(
            asset_id=asset.id,
            asset_version=asset.version,
            asset_sha256=asset.sha256,
            scope=asset.scope,
            library_entity_id=selection.library_entity_id,
            library_version_id=version.id,
            library_version_fingerprint=version.fingerprint,
        ),
        exact_binding.role,
    )


@dataclass(frozen=True, slots=True)
class CreateStartingFrameComposition:
    projects: ProjectRepository
    films: FilmRepository
    library: LibraryRepository
    film_bibles: FilmBibleRepository
    assets: AssetRepository
    clock: Clock
    identifiers: StartingFrameIdentifierFactory
    owner_id: str

    async def __call__(
        self, project_id: str, shot_id: str, draft: StartingFrameDraft
    ) -> StartingFrameComposition:
        await self.projects.get(self.owner_id, project_id)
        shot = await self.films.get_shot(self.owner_id, project_id, shot_id)
        if shot.version != draft.shot_version:
            raise LibraryRevisionConflictError("the shot changed before composition creation")
        binding_revision = await self.film_bibles.get_shot_binding_revision(
            self.owner_id,
            project_id,
            shot_id,
            draft.shot_binding_revision_id,
        )
        if binding_revision.shot_version != shot.version:
            raise DomainValidationError(
                "composition requires bindings for the current shot version"
            )
        if draft.visible_speaker_entity_id is not None and not any(
            pin.entity_id == draft.visible_speaker_entity_id
            and pin.role is FilmBiblePinRole.CHARACTER_IDENTITY
            for pin in binding_revision.bindings
        ):
            raise DomainValidationError(
                "visible speaker must have a character identity in the shot binding"
            )
        layers: list[StartingFrameLayer] = []
        for layer in draft.layers:
            source, source_reference_role = await _composition_asset_snapshot(
                selection=layer.source,
                project_id=project_id,
                binding_revision=binding_revision,
                assets=self.assets,
                library=self.library,
                owner_id=self.owner_id,
            )
            mask_result = (
                None
                if layer.mask is None
                else await _composition_asset_snapshot(
                    selection=layer.mask,
                    project_id=project_id,
                    binding_revision=binding_revision,
                    assets=self.assets,
                    library=self.library,
                    owner_id=self.owner_id,
                )
            )
            mask = mask_result[0] if mask_result is not None else None
            if (
                draft.mode is StartingFrameMode.COMPOSED_UPLOAD
                and source.scope is AssetScope.LIBRARY
                and source_reference_role is not ReferenceRole.STARTING_FRAME
            ):
                raise DomainValidationError(
                    "a library composed upload must be approved for the starting-frame role"
                )
            if draft.mode is StartingFrameMode.LAYERED and layer.role in {
                CompositionLayerRole.BACKGROUND,
                CompositionLayerRole.CHARACTER,
                CompositionLayerRole.PROP,
            }:
                if source.scope is not AssetScope.LIBRARY or source.library_entity_id is None:
                    raise DomainValidationError(
                        "background, character, and prop layers require approved library sources"
                    )
                entity = await self.library.get_entity(self.owner_id, source.library_entity_id)
                compatible_kinds = {
                    CompositionLayerRole.BACKGROUND: {
                        LibraryEntityKind.LOCATION,
                        LibraryEntityKind.SHOT_REFERENCE,
                    },
                    CompositionLayerRole.CHARACTER: {LibraryEntityKind.CHARACTER},
                    CompositionLayerRole.PROP: {LibraryEntityKind.PROP},
                }
                if entity.kind not in compatible_kinds[layer.role]:
                    raise DomainValidationError(
                        "composition layer role is incompatible with its library entity"
                    )
                compatible_roles = {
                    CompositionLayerRole.BACKGROUND: {
                        ReferenceRole.LOCATION_OR_PROP,
                        ReferenceRole.SOURCE_LAYER,
                    },
                    CompositionLayerRole.CHARACTER: {
                        ReferenceRole.IDENTITY_APPEARANCE,
                        ReferenceRole.SOURCE_LAYER,
                    },
                    CompositionLayerRole.PROP: {
                        ReferenceRole.LOCATION_OR_PROP,
                        ReferenceRole.SOURCE_LAYER,
                    },
                }
                if source_reference_role not in compatible_roles[layer.role]:
                    raise DomainValidationError(
                        "library asset role is incompatible with the composition layer"
                    )
            layers.append(
                StartingFrameLayer(
                    role=layer.role,
                    source=source,
                    transform=layer.transform,
                    mask=mask,
                )
            )
        composition = StartingFrameComposition.create(
            composition_id=self.identifiers.new_starting_frame_composition_id(),
            project_id=project_id,
            owner_id=self.owner_id,
            shot_id=shot_id,
            shot_version=shot.version,
            shot_binding_revision_id=binding_revision.id,
            revision=await self.film_bibles.next_starting_frame_revision(
                self.owner_id, project_id, shot_id
            ),
            mode=draft.mode,
            canvas_width=draft.canvas_width,
            canvas_height=draft.canvas_height,
            background_rgba=draft.background_rgba,
            output_rights=draft.output_rights,
            framing_notes=draft.framing_notes,
            pose_notes=draft.pose_notes,
            action_notes=draft.action_notes,
            lighting_notes=draft.lighting_notes,
            visible_speaker_entity_id=draft.visible_speaker_entity_id,
            layers=tuple(layers),
            now=self.clock.now(),
        )
        return await self.film_bibles.create_starting_frame_composition(composition)


@dataclass(frozen=True, slots=True)
class ListStartingFrameCompositions:
    projects: ProjectRepository
    films: FilmRepository
    film_bibles: FilmBibleRepository
    owner_id: str

    async def __call__(
        self, project_id: str, shot_id: str, *, limit: int = 100
    ) -> tuple[StartingFrameComposition, ...]:
        if not 1 <= limit <= 100:
            raise ValueError("composition list limit must be between 1 and 100")
        await self.projects.get(self.owner_id, project_id)
        await self.films.get_shot(self.owner_id, project_id, shot_id)
        return await self.film_bibles.list_starting_frame_compositions(
            self.owner_id, project_id, shot_id, limit=limit
        )


@dataclass(frozen=True, slots=True)
class RenderStartingFrameComposition:
    projects: ProjectRepository
    films: FilmRepository
    film_bibles: FilmBibleRepository
    assets: AssetRepository
    content: StartingFrameContentStore
    renderer: StartingFrameRenderer
    clock: Clock
    asset_identifiers: AssetIdentifierFactory
    owner_id: str

    async def __call__(
        self, project_id: str, shot_id: str, composition_id: str
    ) -> StartingFrameComposition:
        await self.projects.get(self.owner_id, project_id)
        await self.films.get_shot(self.owner_id, project_id, shot_id)
        composition = await self.film_bibles.get_starting_frame_composition(
            self.owner_id, project_id, shot_id, composition_id
        )
        if composition.status is not StartingFrameStatus.DRAFT:
            raise DomainValidationError("only draft compositions can be rendered")
        snapshots = tuple(
            snapshot
            for layer in composition.layers
            for snapshot in (layer.source, layer.mask)
            if snapshot is not None
        )
        source_paths: dict[str, Path] = {}
        for snapshot in snapshots:
            asset = await self.assets.get_owner(self.owner_id, snapshot.asset_id)
            if asset.version != snapshot.asset_version or asset.sha256 != snapshot.asset_sha256:
                raise LibraryRevisionConflictError("a composition source no longer matches its pin")
            source_paths[asset.id] = self.content.resolve_for_read(asset.storage_key)
        candidate = await self.renderer.render(composition, source_paths)
        try:
            stored = await self.content.store_generated_image(
                filename=f"{composition.id}.png", candidate_path=candidate
            )
        except BaseException:
            await self.renderer.discard_candidate(candidate)
            raise
        now = self.clock.now()
        asset = MediaAsset(
            id=self.asset_identifiers.new_asset_id(),
            project_id=project_id,
            owner_id=self.owner_id,
            version=1,
            kind=AssetKind.IMAGE,
            state=AssetState.READY,
            original_filename=stored.filename,
            media_type=stored.media_type,
            storage_key=stored.storage_key,
            size_bytes=stored.size_bytes,
            sha256=stored.sha256,
            rights=composition.output_rights,
            created_at=now,
            scope=AssetScope.PROJECT,
        )
        rendered = composition.with_rendered_asset(
            asset_id=asset.id,
            asset_version=asset.version,
            asset_sha256=asset.sha256,
            renderer_revision=self.renderer.revision,
            now=now,
        )
        try:
            return await self.film_bibles.publish_starting_frame_render(rendered, asset)
        except BaseException:
            await self.content.delete(stored.storage_key)
            raise


@dataclass(frozen=True, slots=True)
class ApproveStartingFrameComposition:
    projects: ProjectRepository
    films: FilmRepository
    film_bibles: FilmBibleRepository
    assets: AssetRepository
    clock: Clock
    owner_id: str

    async def __call__(
        self, project_id: str, shot_id: str, composition_id: str
    ) -> StartingFrameComposition:
        await self.projects.get(self.owner_id, project_id)
        await self.films.get_shot(self.owner_id, project_id, shot_id)
        current = await self.film_bibles.get_starting_frame_composition(
            self.owner_id, project_id, shot_id, composition_id
        )
        if current.rendered_asset_id is None:
            raise DomainValidationError("composition must be rendered before approval")
        output = await self.assets.get(self.owner_id, project_id, current.rendered_asset_id)
        if (
            output.version != current.rendered_asset_version
            or output.sha256 != current.rendered_sha256
        ):
            raise LibraryRevisionConflictError(
                "rendered preview no longer matches its approval pin"
            )
        return await self.film_bibles.approve_starting_frame_composition(
            current.approve(now=self.clock.now())
        )


@dataclass(frozen=True, slots=True)
class GetStartingFramePreview:
    projects: ProjectRepository
    films: FilmRepository
    film_bibles: FilmBibleRepository
    assets: AssetRepository
    content: StartingFrameContentStore
    owner_id: str

    async def __call__(self, project_id: str, shot_id: str, composition_id: str) -> Path:
        await self.projects.get(self.owner_id, project_id)
        await self.films.get_shot(self.owner_id, project_id, shot_id)
        composition = await self.film_bibles.get_starting_frame_composition(
            self.owner_id, project_id, shot_id, composition_id
        )
        if composition.rendered_asset_id is None:
            raise DomainValidationError("composition has not been rendered")
        asset = await self.assets.get(self.owner_id, project_id, composition.rendered_asset_id)
        if asset.sha256 != composition.rendered_sha256:
            raise LibraryRevisionConflictError("preview bytes no longer match the composition")
        return self.content.resolve_for_read(asset.storage_key)


async def _reference_video_source_snapshot(
    *,
    selection: ReferenceVideoSelection,
    purpose: ReferenceVideoPurpose,
    project_id: str,
    binding_revision: ShotBindingRevision,
    assets: AssetRepository,
    library: LibraryRepository,
    owner_id: str,
) -> ReferenceVideoSourceSnapshot:
    asset = await assets.get_owner(owner_id, selection.asset_id)
    if asset.kind is not AssetKind.VIDEO or asset.state is not AssetState.INSPECTED:
        raise DomainValidationError("reference guidance requires an inspected video asset")
    metadata = asset.metadata
    if (
        metadata is None
        or asset.inspector_revision is None
        or metadata.width is None
        or metadata.height is None
        or metadata.frame_rate_numerator is None
        or metadata.frame_rate_denominator is None
    ):
        raise DomainValidationError("reference video requires complete measured video metadata")
    if asset.scope is AssetScope.PROJECT:
        if asset.project_id != project_id:
            raise DomainValidationError("project reference video must belong to this project")
        if selection.library_entity_id is not None or selection.library_version_id is not None:
            raise DomainValidationError("project reference video cannot claim library provenance")
        return ReferenceVideoSourceSnapshot(
            asset_id=asset.id,
            asset_version=asset.version,
            asset_sha256=asset.sha256,
            media_type=asset.media_type,
            scope=asset.scope,
            inspector_revision=asset.inspector_revision,
            duration_ms=metadata.duration_ms,
            width=metadata.width,
            height=metadata.height,
            frame_rate_numerator=metadata.frame_rate_numerator,
            frame_rate_denominator=metadata.frame_rate_denominator,
        )
    if selection.library_entity_id is None or selection.library_version_id is None:
        raise DomainValidationError("library reference video requires exact provenance")
    pin = next(
        (
            candidate
            for candidate in binding_revision.bindings
            if candidate.entity_id == selection.library_entity_id
            and candidate.library_version_id == selection.library_version_id
        ),
        None,
    )
    if pin is None:
        raise DomainValidationError("library reference video is not pinned by this shot")
    version = await library.get_version(
        owner_id, selection.library_entity_id, selection.library_version_id
    )
    if version.status is not LibraryVersionStatus.APPROVED:
        raise DomainValidationError("library reference video requires an approved version")
    if version.fingerprint != pin.version_fingerprint:
        raise DomainValidationError("library reference version no longer matches its shot pin")
    exact_binding = next(
        (candidate for candidate in version.bindings if candidate.asset_id == asset.id), None
    )
    if (
        exact_binding is None
        or exact_binding.asset_version != asset.version
        or exact_binding.asset_sha256 != asset.sha256
    ):
        raise DomainValidationError("reference video is not an exact asset in the selected version")
    if exact_binding.role.value != purpose.value:
        raise DomainValidationError("reference-video purpose must match its approved library role")
    return ReferenceVideoSourceSnapshot(
        asset_id=asset.id,
        asset_version=asset.version,
        asset_sha256=asset.sha256,
        media_type=asset.media_type,
        scope=asset.scope,
        inspector_revision=asset.inspector_revision,
        duration_ms=metadata.duration_ms,
        width=metadata.width,
        height=metadata.height,
        frame_rate_numerator=metadata.frame_rate_numerator,
        frame_rate_denominator=metadata.frame_rate_denominator,
        library_entity_id=selection.library_entity_id,
        library_version_id=version.id,
        library_version_fingerprint=version.fingerprint,
    )


@dataclass(frozen=True, slots=True)
class CreateReferenceVideoGuidance:
    projects: ProjectRepository
    films: FilmRepository
    library: LibraryRepository
    film_bibles: FilmBibleRepository
    assets: AssetRepository
    clock: Clock
    identifiers: StartingFrameIdentifierFactory
    owner_id: str

    async def __call__(
        self, project_id: str, shot_id: str, draft: ReferenceVideoGuidanceDraft
    ) -> ReferenceVideoGuidance:
        await self.projects.get(self.owner_id, project_id)
        shot = await self.films.get_shot(self.owner_id, project_id, shot_id)
        if shot.version != draft.shot_version:
            raise LibraryRevisionConflictError("the shot changed before guidance creation")
        binding_revision = await self.film_bibles.get_shot_binding_revision(
            self.owner_id,
            project_id,
            shot_id,
            draft.shot_binding_revision_id,
        )
        if binding_revision.shot_version != shot.version:
            raise DomainValidationError("reference guidance requires current shot bindings")
        source = await _reference_video_source_snapshot(
            selection=draft.source,
            purpose=draft.purpose,
            project_id=project_id,
            binding_revision=binding_revision,
            assets=self.assets,
            library=self.library,
            owner_id=self.owner_id,
        )
        guidance = ReferenceVideoGuidance.create(
            guidance_id=self.identifiers.new_reference_video_guidance_id(),
            project_id=project_id,
            owner_id=self.owner_id,
            shot_id=shot_id,
            shot_version=shot.version,
            shot_binding_revision_id=binding_revision.id,
            revision=await self.film_bibles.next_reference_guidance_revision(
                self.owner_id, project_id, shot_id
            ),
            purpose=draft.purpose,
            source=source,
            trim_start_ms=draft.trim_start_ms,
            trim_end_ms=draft.trim_end_ms,
            guidance_notes=draft.guidance_notes,
            now=self.clock.now(),
        )
        return await self.film_bibles.create_reference_video_guidance(guidance)


@dataclass(frozen=True, slots=True)
class ListReferenceVideoGuidance:
    projects: ProjectRepository
    films: FilmRepository
    film_bibles: FilmBibleRepository
    owner_id: str

    async def __call__(
        self, project_id: str, shot_id: str, *, limit: int = 100
    ) -> tuple[ReferenceVideoGuidance, ...]:
        if not 1 <= limit <= 100:
            raise ValueError("reference-guidance list limit must be between 1 and 100")
        await self.projects.get(self.owner_id, project_id)
        await self.films.get_shot(self.owner_id, project_id, shot_id)
        return await self.film_bibles.list_reference_video_guidance(
            self.owner_id, project_id, shot_id, limit=limit
        )


async def _verify_reference_guidance_source(
    guidance: ReferenceVideoGuidance,
    *,
    assets: AssetRepository,
    owner_id: str,
) -> MediaAsset:
    asset = await assets.get_owner(owner_id, guidance.source.asset_id)
    if (
        asset.version != guidance.source.asset_version
        or asset.sha256 != guidance.source.asset_sha256
        or asset.state is not AssetState.INSPECTED
        or asset.inspector_revision != guidance.source.inspector_revision
    ):
        raise LibraryRevisionConflictError("reference-video source no longer matches its pin")
    return asset


@dataclass(frozen=True, slots=True)
class ApproveReferenceVideoGuidance:
    projects: ProjectRepository
    films: FilmRepository
    library: LibraryRepository
    film_bibles: FilmBibleRepository
    assets: AssetRepository
    clock: Clock
    owner_id: str

    async def __call__(
        self, project_id: str, shot_id: str, guidance_id: str
    ) -> ReferenceVideoGuidance:
        await self.projects.get(self.owner_id, project_id)
        shot = await self.films.get_shot(self.owner_id, project_id, shot_id)
        guidance = await self.film_bibles.get_reference_video_guidance(
            self.owner_id, project_id, shot_id, guidance_id
        )
        if guidance.shot_version != shot.version:
            raise LibraryRevisionConflictError("the shot changed before guidance approval")
        await _verify_reference_guidance_source(
            guidance, assets=self.assets, owner_id=self.owner_id
        )
        if guidance.source.scope is AssetScope.LIBRARY:
            assert guidance.source.library_entity_id is not None
            assert guidance.source.library_version_id is not None
            version = await self.library.get_version(
                self.owner_id,
                guidance.source.library_entity_id,
                guidance.source.library_version_id,
            )
            if (
                version.status is not LibraryVersionStatus.APPROVED
                or version.fingerprint != guidance.source.library_version_fingerprint
            ):
                raise LibraryRevisionConflictError(
                    "reference-video library provenance is no longer approved"
                )
            exact_binding = next(
                (
                    candidate
                    for candidate in version.bindings
                    if candidate.asset_id == guidance.source.asset_id
                ),
                None,
            )
            if (
                exact_binding is None
                or exact_binding.asset_version != guidance.source.asset_version
                or exact_binding.asset_sha256 != guidance.source.asset_sha256
                or exact_binding.role.value != guidance.purpose.value
            ):
                raise LibraryRevisionConflictError(
                    "reference-video library binding no longer matches its approval pin"
                )
        return await self.film_bibles.approve_reference_video_guidance(
            guidance.approve(now=self.clock.now())
        )


@dataclass(frozen=True, slots=True)
class ReferenceVideoPreview:
    path: Path
    media_type: str


@dataclass(frozen=True, slots=True)
class GetReferenceVideoPreview:
    projects: ProjectRepository
    films: FilmRepository
    film_bibles: FilmBibleRepository
    assets: AssetRepository
    content: AssetContentStore
    owner_id: str

    async def __call__(
        self, project_id: str, shot_id: str, guidance_id: str
    ) -> ReferenceVideoPreview:
        await self.projects.get(self.owner_id, project_id)
        await self.films.get_shot(self.owner_id, project_id, shot_id)
        guidance = await self.film_bibles.get_reference_video_guidance(
            self.owner_id, project_id, shot_id, guidance_id
        )
        asset = await _verify_reference_guidance_source(
            guidance, assets=self.assets, owner_id=self.owner_id
        )
        return ReferenceVideoPreview(
            path=self.content.resolve_for_read(asset.storage_key),
            media_type=asset.media_type,
        )
