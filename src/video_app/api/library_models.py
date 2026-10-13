"""HTTP models for the reusable film-library v2 contract."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from video_app.application.library import (
    CompositionAssetSelection,
    FilmBiblePinSelection,
    LibraryAssetSelection,
    LibraryVersionDraft,
    ReferenceVideoGuidanceDraft,
    ReferenceVideoSelection,
    StartingFrameDraft,
    StartingFrameLayerDraft,
)
from video_app.domain.assets import AssetScope, RightsDeclaration
from video_app.domain.library import (
    CompositionAssetSnapshot,
    CompositionFit,
    CompositionLayerRole,
    FilmBibleNameResolution,
    FilmBiblePin,
    FilmBiblePinRole,
    FilmBibleSnapshot,
    FilmBibleStatus,
    LayerTransform,
    LibraryEntity,
    LibraryEntityKind,
    LibraryVersion,
    LibraryVersionKind,
    LibraryVersionStatus,
    NameResolutionStatus,
    ReferenceGuidanceStatus,
    ReferenceRole,
    ReferenceVideoGuidance,
    ReferenceVideoPurpose,
    ReferenceVideoSourceSnapshot,
    ShotBindingRevision,
    SourceCrop,
    StartingFrameComposition,
    StartingFrameLayer,
    StartingFrameMode,
    StartingFrameStatus,
)


class LibraryEntityDraftModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: LibraryEntityKind
    display_name: str = Field(min_length=1, max_length=200)
    aliases: tuple[str, ...] = Field(default=(), max_length=50)


class LibraryEntityUpdateModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    display_name: str = Field(min_length=1, max_length=200)
    aliases: tuple[str, ...] = Field(default=(), max_length=50)


class LibraryEntityModel(BaseModel):
    id: str
    kind: LibraryEntityKind
    metadata_version: int
    display_name: str
    aliases: tuple[str, ...]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, entity: LibraryEntity) -> LibraryEntityModel:
        return cls(
            id=entity.id,
            kind=entity.kind,
            metadata_version=entity.metadata_version,
            display_name=entity.display_name,
            aliases=entity.aliases,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )


class LibraryEntityListModel(BaseModel):
    items: tuple[LibraryEntityModel, ...]


class LibraryAssetSelectionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str = Field(min_length=1)
    role: ReferenceRole
    view_label: str | None = Field(default=None, min_length=1, max_length=100)

    def to_domain(self) -> LibraryAssetSelection:
        return LibraryAssetSelection(
            asset_id=self.asset_id,
            role=self.role,
            view_label=self.view_label,
        )


class LibraryVersionDraftModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: LibraryVersionKind
    label: str = Field(min_length=1, max_length=200)
    notes: str = Field(default="", max_length=4_000)
    invariants: str = Field(default="", max_length=4_000)
    state_notes: str = Field(default="", max_length=4_000)
    voice_profile_id: str | None = Field(default=None, min_length=1, max_length=200)
    rights_statement: str = Field(default="", max_length=4_000)
    assets: tuple[LibraryAssetSelectionModel, ...] = Field(min_length=1, max_length=50)

    def to_domain(self) -> LibraryVersionDraft:
        return LibraryVersionDraft(
            kind=self.kind,
            label=self.label,
            notes=self.notes,
            invariants=self.invariants,
            state_notes=self.state_notes,
            voice_profile_id=self.voice_profile_id,
            rights_statement=self.rights_statement,
            assets=tuple(asset.to_domain() for asset in self.assets),
        )


class LibraryAssetBindingModel(BaseModel):
    asset_id: str
    asset_version: int
    asset_sha256: str
    role: ReferenceRole
    view_label: str | None


class LibraryVersionModel(BaseModel):
    id: str
    entity_id: str
    version_number: int
    kind: LibraryVersionKind
    status: LibraryVersionStatus
    label: str
    notes: str
    invariants: str
    state_notes: str
    voice_profile_id: str | None
    rights_statement: str
    assets: tuple[LibraryAssetBindingModel, ...]
    fingerprint: str
    created_at: datetime
    approved_at: datetime | None

    @classmethod
    def from_domain(cls, version: LibraryVersion) -> LibraryVersionModel:
        return cls(
            id=version.id,
            entity_id=version.entity_id,
            version_number=version.version_number,
            kind=version.kind,
            status=version.status,
            label=version.label,
            notes=version.notes,
            invariants=version.invariants,
            state_notes=version.state_notes,
            voice_profile_id=version.voice_profile_id,
            rights_statement=version.rights_statement,
            assets=tuple(
                LibraryAssetBindingModel(
                    asset_id=binding.asset_id,
                    asset_version=binding.asset_version,
                    asset_sha256=binding.asset_sha256,
                    role=binding.role,
                    view_label=binding.view_label,
                )
                for binding in version.bindings
            ),
            fingerprint=version.fingerprint,
            created_at=version.created_at,
            approved_at=version.approved_at,
        )


class LibraryVersionListModel(BaseModel):
    items: tuple[LibraryVersionModel, ...]


class FilmBiblePinSelectionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str = Field(min_length=1)
    version_id: str = Field(min_length=1)
    role: FilmBiblePinRole

    def to_domain(self) -> FilmBiblePinSelection:
        return FilmBiblePinSelection(
            entity_id=self.entity_id,
            version_id=self.version_id,
            role=self.role,
        )


class FilmBibleSnapshotDraftModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pins: tuple[FilmBiblePinSelectionModel, ...] = Field(min_length=1, max_length=100)


class FilmBiblePinModel(BaseModel):
    entity_id: str
    library_version_id: str
    library_version_number: int
    version_kind: LibraryVersionKind
    version_fingerprint: str
    role: FilmBiblePinRole

    @classmethod
    def from_domain(cls, pin: FilmBiblePin) -> FilmBiblePinModel:
        return cls(
            entity_id=pin.entity_id,
            library_version_id=pin.library_version_id,
            library_version_number=pin.library_version_number,
            version_kind=pin.version_kind,
            version_fingerprint=pin.version_fingerprint,
            role=pin.role,
        )


class FilmBibleSnapshotModel(BaseModel):
    id: str
    project_id: str
    revision: int
    status: FilmBibleStatus
    pins: tuple[FilmBiblePinModel, ...]
    fingerprint: str
    created_at: datetime
    approved_at: datetime | None

    @classmethod
    def from_domain(cls, snapshot: FilmBibleSnapshot) -> FilmBibleSnapshotModel:
        return cls(
            id=snapshot.id,
            project_id=snapshot.project_id,
            revision=snapshot.revision,
            status=snapshot.status,
            pins=tuple(FilmBiblePinModel.from_domain(pin) for pin in snapshot.pins),
            fingerprint=snapshot.fingerprint,
            created_at=snapshot.created_at,
            approved_at=snapshot.approved_at,
        )


class FilmBibleSnapshotListModel(BaseModel):
    items: tuple[FilmBibleSnapshotModel, ...]


class FilmBibleResolutionCandidateModel(BaseModel):
    entity_id: str
    display_name: str
    entity_kind: LibraryEntityKind
    pins: tuple[FilmBiblePinModel, ...]


class FilmBibleNameResolutionModel(BaseModel):
    mention: str
    status: NameResolutionStatus
    candidates: tuple[FilmBibleResolutionCandidateModel, ...]

    @classmethod
    def from_domain(cls, result: FilmBibleNameResolution) -> FilmBibleNameResolutionModel:
        return cls(
            mention=result.mention,
            status=result.status,
            candidates=tuple(
                FilmBibleResolutionCandidateModel(
                    entity_id=candidate.entity_id,
                    display_name=candidate.display_name,
                    entity_kind=candidate.entity_kind,
                    pins=tuple(FilmBiblePinModel.from_domain(pin) for pin in candidate.pins),
                )
                for candidate in result.candidates
            ),
        )


class ShotBindingRevisionDraftModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shot_version: int = Field(ge=1)
    film_bible_snapshot_id: str = Field(min_length=1)
    bindings: tuple[FilmBiblePinSelectionModel, ...] = Field(min_length=1, max_length=100)


class ShotBindingRevisionModel(BaseModel):
    id: str
    project_id: str
    shot_id: str
    shot_version: int
    revision: int
    film_bible_snapshot_id: str
    bindings: tuple[FilmBiblePinModel, ...]
    fingerprint: str
    created_at: datetime

    @classmethod
    def from_domain(cls, revision: ShotBindingRevision) -> ShotBindingRevisionModel:
        return cls(
            id=revision.id,
            project_id=revision.project_id,
            shot_id=revision.shot_id,
            shot_version=revision.shot_version,
            revision=revision.revision,
            film_bible_snapshot_id=revision.film_bible_snapshot_id,
            bindings=tuple(FilmBiblePinModel.from_domain(pin) for pin in revision.bindings),
            fingerprint=revision.fingerprint,
            created_at=revision.created_at,
        )


class ShotBindingRevisionListModel(BaseModel):
    items: tuple[ShotBindingRevisionModel, ...]


class AffectedShotListModel(BaseModel):
    entity_id: str
    library_version_id: str
    shot_ids: tuple[str, ...]


class CompositionAssetSelectionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str = Field(min_length=1)
    library_entity_id: str | None = Field(default=None, min_length=1)
    library_version_id: str | None = Field(default=None, min_length=1)

    def to_domain(self) -> CompositionAssetSelection:
        return CompositionAssetSelection(
            asset_id=self.asset_id,
            library_entity_id=self.library_entity_id,
            library_version_id=self.library_version_id,
        )


class SourceCropModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(ge=1, le=8192)
    height: int = Field(ge=1, le=8192)

    def to_domain(self) -> SourceCrop:
        return SourceCrop(x=self.x, y=self.y, width=self.width, height=self.height)


class LayerTransformModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: int = Field(ge=-16_384, le=16_384)
    y: int = Field(ge=-16_384, le=16_384)
    width: int = Field(ge=1, le=8192)
    height: int = Field(ge=1, le=8192)
    rotation_millidegrees: int = Field(default=0, ge=-360_000, le=360_000)
    opacity_basis_points: int = Field(default=10_000, ge=0, le=10_000)
    fit: CompositionFit = CompositionFit.CONTAIN
    crop: SourceCropModel | None = None

    def to_domain(self) -> LayerTransform:
        return LayerTransform(
            x=self.x,
            y=self.y,
            width=self.width,
            height=self.height,
            rotation_millidegrees=self.rotation_millidegrees,
            opacity_basis_points=self.opacity_basis_points,
            fit=self.fit,
            crop=self.crop.to_domain() if self.crop is not None else None,
        )


class StartingFrameLayerDraftModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: CompositionLayerRole
    source: CompositionAssetSelectionModel
    transform: LayerTransformModel
    mask: CompositionAssetSelectionModel | None = None

    def to_domain(self) -> StartingFrameLayerDraft:
        return StartingFrameLayerDraft(
            role=self.role,
            source=self.source.to_domain(),
            transform=self.transform.to_domain(),
            mask=self.mask.to_domain() if self.mask is not None else None,
        )


class StartingFrameDraftModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shot_version: int = Field(ge=1)
    shot_binding_revision_id: str = Field(min_length=1)
    mode: StartingFrameMode
    canvas_width: int = Field(ge=64, le=4096)
    canvas_height: int = Field(ge=64, le=4096)
    background_rgba: str = Field(pattern=r"^#[0-9A-Fa-f]{8}$")
    output_rights: RightsDeclaration
    framing_notes: str = Field(default="", max_length=2000)
    pose_notes: str = Field(default="", max_length=2000)
    action_notes: str = Field(default="", max_length=2000)
    lighting_notes: str = Field(default="", max_length=2000)
    visible_speaker_entity_id: str | None = Field(default=None, min_length=1)
    layers: tuple[StartingFrameLayerDraftModel, ...] = Field(min_length=1, max_length=32)

    def to_domain(self) -> StartingFrameDraft:
        return StartingFrameDraft(
            shot_version=self.shot_version,
            shot_binding_revision_id=self.shot_binding_revision_id,
            mode=self.mode,
            canvas_width=self.canvas_width,
            canvas_height=self.canvas_height,
            background_rgba=self.background_rgba,
            output_rights=self.output_rights,
            framing_notes=self.framing_notes,
            pose_notes=self.pose_notes,
            action_notes=self.action_notes,
            lighting_notes=self.lighting_notes,
            visible_speaker_entity_id=self.visible_speaker_entity_id,
            layers=tuple(layer.to_domain() for layer in self.layers),
        )


class CompositionAssetSnapshotModel(BaseModel):
    asset_id: str
    asset_version: int
    asset_sha256: str
    scope: AssetScope
    library_entity_id: str | None
    library_version_id: str | None
    library_version_fingerprint: str | None

    @classmethod
    def from_domain(cls, snapshot: CompositionAssetSnapshot) -> CompositionAssetSnapshotModel:
        return cls(
            asset_id=snapshot.asset_id,
            asset_version=snapshot.asset_version,
            asset_sha256=snapshot.asset_sha256,
            scope=snapshot.scope,
            library_entity_id=snapshot.library_entity_id,
            library_version_id=snapshot.library_version_id,
            library_version_fingerprint=snapshot.library_version_fingerprint,
        )


class StartingFrameLayerModel(BaseModel):
    role: CompositionLayerRole
    source: CompositionAssetSnapshotModel
    transform: LayerTransformModel
    mask: CompositionAssetSnapshotModel | None

    @classmethod
    def from_domain(cls, layer: StartingFrameLayer) -> StartingFrameLayerModel:
        crop = layer.transform.crop
        return cls(
            role=layer.role,
            source=CompositionAssetSnapshotModel.from_domain(layer.source),
            transform=LayerTransformModel(
                x=layer.transform.x,
                y=layer.transform.y,
                width=layer.transform.width,
                height=layer.transform.height,
                rotation_millidegrees=layer.transform.rotation_millidegrees,
                opacity_basis_points=layer.transform.opacity_basis_points,
                fit=layer.transform.fit,
                crop=(
                    SourceCropModel(x=crop.x, y=crop.y, width=crop.width, height=crop.height)
                    if crop is not None
                    else None
                ),
            ),
            mask=(
                CompositionAssetSnapshotModel.from_domain(layer.mask)
                if layer.mask is not None
                else None
            ),
        )


class StartingFrameCompositionModel(BaseModel):
    id: str
    project_id: str
    shot_id: str
    shot_version: int
    shot_binding_revision_id: str
    revision: int
    mode: StartingFrameMode
    status: StartingFrameStatus
    canvas_width: int
    canvas_height: int
    background_rgba: str
    output_rights: RightsDeclaration
    framing_notes: str
    pose_notes: str
    action_notes: str
    lighting_notes: str
    visible_speaker_entity_id: str | None
    layers: tuple[StartingFrameLayerModel, ...]
    fingerprint: str
    created_at: datetime
    rendered_asset_id: str | None
    rendered_asset_version: int | None
    rendered_sha256: str | None
    renderer_revision: str | None
    rendered_at: datetime | None
    approved_at: datetime | None
    preview_url: str | None

    @classmethod
    def from_domain(cls, value: StartingFrameComposition) -> StartingFrameCompositionModel:
        preview_url = (
            None
            if value.rendered_asset_id is None
            else (
                f"/api/v2/projects/{value.project_id}/film/shots/{value.shot_id}/"
                f"starting-frames/{value.id}/preview"
            )
        )
        return cls(
            id=value.id,
            project_id=value.project_id,
            shot_id=value.shot_id,
            shot_version=value.shot_version,
            shot_binding_revision_id=value.shot_binding_revision_id,
            revision=value.revision,
            mode=value.mode,
            status=value.status,
            canvas_width=value.canvas_width,
            canvas_height=value.canvas_height,
            background_rgba=value.background_rgba,
            output_rights=value.output_rights,
            framing_notes=value.framing_notes,
            pose_notes=value.pose_notes,
            action_notes=value.action_notes,
            lighting_notes=value.lighting_notes,
            visible_speaker_entity_id=value.visible_speaker_entity_id,
            layers=tuple(StartingFrameLayerModel.from_domain(layer) for layer in value.layers),
            fingerprint=value.fingerprint,
            created_at=value.created_at,
            rendered_asset_id=value.rendered_asset_id,
            rendered_asset_version=value.rendered_asset_version,
            rendered_sha256=value.rendered_sha256,
            renderer_revision=value.renderer_revision,
            rendered_at=value.rendered_at,
            approved_at=value.approved_at,
            preview_url=preview_url,
        )


class StartingFrameCompositionListModel(BaseModel):
    items: tuple[StartingFrameCompositionModel, ...]


class ReferenceVideoSelectionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str = Field(min_length=1)
    library_entity_id: str | None = None
    library_version_id: str | None = None

    def to_domain(self) -> ReferenceVideoSelection:
        return ReferenceVideoSelection(
            asset_id=self.asset_id,
            library_entity_id=self.library_entity_id,
            library_version_id=self.library_version_id,
        )


class ReferenceVideoGuidanceDraftModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shot_version: int = Field(ge=1)
    shot_binding_revision_id: str = Field(min_length=1)
    purpose: ReferenceVideoPurpose
    source: ReferenceVideoSelectionModel
    trim_start_ms: int = Field(ge=0)
    trim_end_ms: int = Field(gt=0)
    guidance_notes: str = Field(default="", max_length=2_000)

    def to_domain(self) -> ReferenceVideoGuidanceDraft:
        return ReferenceVideoGuidanceDraft(
            shot_version=self.shot_version,
            shot_binding_revision_id=self.shot_binding_revision_id,
            purpose=self.purpose,
            source=self.source.to_domain(),
            trim_start_ms=self.trim_start_ms,
            trim_end_ms=self.trim_end_ms,
            guidance_notes=self.guidance_notes,
        )


class ReferenceVideoSourceSnapshotModel(BaseModel):
    asset_id: str
    asset_version: int
    asset_sha256: str
    media_type: str
    scope: AssetScope
    inspector_revision: str
    duration_ms: int
    width: int
    height: int
    frame_rate_numerator: int
    frame_rate_denominator: int
    library_entity_id: str | None
    library_version_id: str | None
    library_version_fingerprint: str | None

    @classmethod
    def from_domain(cls, source: ReferenceVideoSourceSnapshot) -> ReferenceVideoSourceSnapshotModel:
        return cls(**{field: getattr(source, field) for field in cls.model_fields})


class ReferenceVideoGuidanceModel(BaseModel):
    id: str
    project_id: str
    shot_id: str
    shot_version: int
    shot_binding_revision_id: str
    revision: int
    purpose: ReferenceVideoPurpose
    source: ReferenceVideoSourceSnapshotModel
    trim_start_ms: int
    trim_end_ms: int
    guidance_notes: str
    status: ReferenceGuidanceStatus
    fingerprint: str
    created_at: datetime
    approved_at: datetime | None
    preview_url: str

    @classmethod
    def from_domain(cls, value: ReferenceVideoGuidance) -> ReferenceVideoGuidanceModel:
        return cls(
            id=value.id,
            project_id=value.project_id,
            shot_id=value.shot_id,
            shot_version=value.shot_version,
            shot_binding_revision_id=value.shot_binding_revision_id,
            revision=value.revision,
            purpose=value.purpose,
            source=ReferenceVideoSourceSnapshotModel.from_domain(value.source),
            trim_start_ms=value.trim_start_ms,
            trim_end_ms=value.trim_end_ms,
            guidance_notes=value.guidance_notes,
            status=value.status,
            fingerprint=value.fingerprint,
            created_at=value.created_at,
            approved_at=value.approved_at,
            preview_url=(
                f"/api/v2/projects/{value.project_id}/film/shots/{value.shot_id}/"
                f"reference-guidance/{value.id}/preview"
            ),
        )


class ReferenceVideoGuidanceListModel(BaseModel):
    items: tuple[ReferenceVideoGuidanceModel, ...]
