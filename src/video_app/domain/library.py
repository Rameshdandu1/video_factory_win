"""Reusable, owner-scoped film-library entities and immutable versions."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum

from video_app.domain.assets import AssetScope, RightsDeclaration
from video_app.domain.models import DomainValidationError, _require_non_empty, _require_utc_aware


def normalize_display_text(value: str, *, field: str, maximum: int = 200) -> str:
    """Normalize user-facing Unicode without turning it into an identity key."""

    normalized = unicodedata.normalize("NFC", value).strip()
    if not 1 <= len(normalized) <= maximum:
        raise DomainValidationError(f"{field} must contain between 1 and {maximum} characters")
    if "\x00" in normalized:
        raise DomainValidationError(f"{field} must not contain null characters")
    return normalized


def canonical_name(value: str) -> str:
    """Return a Unicode-safe comparison token used only for display-name lookup."""

    return unicodedata.normalize("NFKC", value).strip().casefold()


class LibraryEntityKind(str, Enum):
    CHARACTER = "character"
    LOCATION = "location"
    PROP = "prop"
    SHOT_REFERENCE = "shot_reference"


class LibraryVersionKind(str, Enum):
    IDENTITY = "identity"
    WARDROBE = "wardrobe"
    LOCATION_VIEW = "location_view"
    LIGHTING_VARIANT = "lighting_variant"
    PROP_VARIANT = "prop_variant"
    PROP_STATE = "prop_state"
    SHOT_REFERENCE = "shot_reference"


class ReferenceRole(str, Enum):
    IDENTITY_APPEARANCE = "identity_appearance"
    LOCATION_OR_PROP = "location_or_prop"
    SOURCE_LAYER = "source_layer"
    STARTING_FRAME = "starting_frame"
    MOTION_PERFORMANCE = "motion_performance"
    SHOT_GUIDANCE = "shot_guidance"
    REVIEW_ONLY = "review_only"


class LibraryVersionStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    ARCHIVED = "archived"


class FilmBibleStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"


class FilmBiblePinRole(str, Enum):
    CHARACTER_IDENTITY = "character_identity"
    CHARACTER_WARDROBE = "character_wardrobe"
    LOCATION_VIEW = "location_view"
    LOCATION_LIGHTING = "location_lighting"
    PROP_VARIANT = "prop_variant"
    PROP_STATE = "prop_state"
    SHOT_REFERENCE = "shot_reference"


class NameResolutionStatus(str, Enum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"


class StartingFrameMode(str, Enum):
    COMPOSED_UPLOAD = "composed_upload"
    LAYERED = "layered"


class StartingFrameStatus(str, Enum):
    DRAFT = "draft"
    RENDERED = "rendered"
    APPROVED = "approved"


class ReferenceVideoPurpose(str, Enum):
    MOTION_PERFORMANCE = "motion_performance"
    SHOT_GUIDANCE = "shot_guidance"
    REVIEW_ONLY = "review_only"


class ReferenceGuidanceStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"


class CompositionLayerRole(str, Enum):
    STARTING_FRAME = "starting_frame"
    BACKGROUND = "background"
    CHARACTER = "character"
    PROP = "prop"
    OVERLAY = "overlay"


class CompositionFit(str, Enum):
    CONTAIN = "contain"
    COVER = "cover"
    STRETCH = "stretch"


_COMPATIBLE_VERSION_KINDS: dict[LibraryEntityKind, frozenset[LibraryVersionKind]] = {
    LibraryEntityKind.CHARACTER: frozenset(
        {LibraryVersionKind.IDENTITY, LibraryVersionKind.WARDROBE}
    ),
    LibraryEntityKind.LOCATION: frozenset(
        {LibraryVersionKind.LOCATION_VIEW, LibraryVersionKind.LIGHTING_VARIANT}
    ),
    LibraryEntityKind.PROP: frozenset(
        {LibraryVersionKind.PROP_VARIANT, LibraryVersionKind.PROP_STATE}
    ),
    LibraryEntityKind.SHOT_REFERENCE: frozenset({LibraryVersionKind.SHOT_REFERENCE}),
}

_PIN_ROLE_VERSION_KIND: dict[FilmBiblePinRole, LibraryVersionKind] = {
    FilmBiblePinRole.CHARACTER_IDENTITY: LibraryVersionKind.IDENTITY,
    FilmBiblePinRole.CHARACTER_WARDROBE: LibraryVersionKind.WARDROBE,
    FilmBiblePinRole.LOCATION_VIEW: LibraryVersionKind.LOCATION_VIEW,
    FilmBiblePinRole.LOCATION_LIGHTING: LibraryVersionKind.LIGHTING_VARIANT,
    FilmBiblePinRole.PROP_VARIANT: LibraryVersionKind.PROP_VARIANT,
    FilmBiblePinRole.PROP_STATE: LibraryVersionKind.PROP_STATE,
    FilmBiblePinRole.SHOT_REFERENCE: LibraryVersionKind.SHOT_REFERENCE,
}


@dataclass(frozen=True, slots=True)
class LibraryEntity:
    id: str
    owner_id: str
    kind: LibraryEntityKind
    metadata_version: int
    display_name: str
    aliases: tuple[str, ...]
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        _require_non_empty(self.id, "library entity id")
        _require_non_empty(self.owner_id, "owner id")
        if self.metadata_version < 1:
            raise DomainValidationError("library metadata version must be positive")
        normalized_name = normalize_display_text(self.display_name, field="display name")
        if normalized_name != self.display_name:
            raise DomainValidationError("display name must already be normalized")
        seen = {canonical_name(self.display_name)}
        for alias in self.aliases:
            normalized_alias = normalize_display_text(alias, field="alias")
            if normalized_alias != alias:
                raise DomainValidationError("aliases must already be normalized")
            key = canonical_name(alias)
            if key in seen:
                raise DomainValidationError("display name and aliases must be unique")
            seen.add(key)
        if len(self.aliases) > 50:
            raise DomainValidationError("a library entity supports at most 50 aliases")
        _require_utc_aware(self.created_at, "created_at")
        _require_utc_aware(self.updated_at, "updated_at")
        if self.updated_at < self.created_at:
            raise DomainValidationError("updated_at cannot precede created_at")

    @classmethod
    def create(
        cls,
        *,
        entity_id: str,
        owner_id: str,
        kind: LibraryEntityKind,
        display_name: str,
        aliases: tuple[str, ...],
        now: datetime,
    ) -> LibraryEntity:
        return cls(
            id=entity_id,
            owner_id=owner_id,
            kind=kind,
            metadata_version=1,
            display_name=normalize_display_text(display_name, field="display name"),
            aliases=tuple(normalize_display_text(alias, field="alias") for alias in aliases),
            created_at=now,
            updated_at=now,
        )

    def rename(
        self,
        *,
        display_name: str,
        aliases: tuple[str, ...],
        expected_version: int,
        now: datetime,
    ) -> LibraryEntity:
        if expected_version != self.metadata_version:
            raise LibraryMetadataVersionError("library metadata version does not match")
        _require_utc_aware(now, "updated_at")
        if now < self.updated_at:
            raise DomainValidationError("updated_at cannot precede current library metadata")
        return replace(
            self,
            metadata_version=self.metadata_version + 1,
            display_name=normalize_display_text(display_name, field="display name"),
            aliases=tuple(normalize_display_text(alias, field="alias") for alias in aliases),
            updated_at=now,
        )

    def matches(self, query: str) -> bool:
        token = canonical_name(query)
        return not token or any(
            token in canonical_name(candidate) for candidate in (self.display_name, *self.aliases)
        )


@dataclass(frozen=True, slots=True)
class LibraryAssetBinding:
    asset_id: str
    asset_version: int
    asset_sha256: str
    role: ReferenceRole
    view_label: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.asset_id, "asset id")
        if self.asset_version < 1:
            raise DomainValidationError("asset version must be positive")
        if len(self.asset_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.asset_sha256
        ):
            raise DomainValidationError("asset checksum must be lowercase SHA-256")
        if self.view_label is not None:
            normalized = normalize_display_text(self.view_label, field="view label", maximum=100)
            if normalized != self.view_label:
                raise DomainValidationError("view label must already be normalized")


@dataclass(frozen=True, slots=True)
class LibraryVersion:
    id: str
    entity_id: str
    owner_id: str
    version_number: int
    kind: LibraryVersionKind
    status: LibraryVersionStatus
    label: str
    notes: str
    invariants: str
    state_notes: str
    voice_profile_id: str | None
    rights_statement: str
    bindings: tuple[LibraryAssetBinding, ...]
    fingerprint: str
    created_at: datetime
    approved_at: datetime | None = None

    def __post_init__(self) -> None:
        for value, field in (
            (self.id, "library version id"),
            (self.entity_id, "library entity id"),
            (self.owner_id, "owner id"),
        ):
            _require_non_empty(value, field)
        if self.version_number < 1:
            raise DomainValidationError("library version number must be positive")
        if normalize_display_text(self.label, field="version label") != self.label:
            raise DomainValidationError("version label must already be normalized")
        for value, field in (
            (self.notes, "notes"),
            (self.invariants, "invariants"),
            (self.state_notes, "state notes"),
            (self.rights_statement, "rights statement"),
        ):
            if len(value) > 4_000 or "\x00" in value:
                raise DomainValidationError(f"{field} must contain at most 4000 safe characters")
        if self.voice_profile_id is not None:
            _require_non_empty(self.voice_profile_id, "voice profile id")
        if not self.bindings:
            raise DomainValidationError("library versions require at least one asset binding")
        asset_ids = [binding.asset_id for binding in self.bindings]
        if len(asset_ids) != len(set(asset_ids)):
            raise DomainValidationError("an asset may be bound only once per library version")
        if self.kind is LibraryVersionKind.IDENTITY and not any(
            binding.role is ReferenceRole.IDENTITY_APPEARANCE for binding in self.bindings
        ):
            raise DomainValidationError("identity versions require an identity reference")
        if len(self.fingerprint) != 64 or any(
            character not in "0123456789abcdef" for character in self.fingerprint
        ):
            raise DomainValidationError("library version fingerprint must be lowercase SHA-256")
        _require_utc_aware(self.created_at, "created_at")
        needs_approval_time = self.status in {
            LibraryVersionStatus.APPROVED,
            LibraryVersionStatus.ARCHIVED,
        }
        if needs_approval_time != (self.approved_at is not None):
            raise DomainValidationError("approved status and timestamp must be present together")
        if self.approved_at is not None:
            _require_utc_aware(self.approved_at, "approved_at")
            if self.approved_at < self.created_at:
                raise DomainValidationError("approved_at cannot precede created_at")

    @classmethod
    def create(
        cls,
        *,
        version_id: str,
        entity: LibraryEntity,
        version_number: int,
        kind: LibraryVersionKind,
        label: str,
        notes: str,
        invariants: str,
        state_notes: str,
        voice_profile_id: str | None,
        rights_statement: str,
        bindings: tuple[LibraryAssetBinding, ...],
        now: datetime,
    ) -> LibraryVersion:
        if kind not in _COMPATIBLE_VERSION_KINDS[entity.kind]:
            raise DomainValidationError("version kind is incompatible with the library entity")
        normalized_label = normalize_display_text(label, field="version label")
        normalized_voice = voice_profile_id.strip() if voice_profile_id is not None else None
        payload = {
            "entity_id": entity.id,
            "version_number": version_number,
            "kind": kind.value,
            "label": normalized_label,
            "notes": notes,
            "invariants": invariants,
            "state_notes": state_notes,
            "voice_profile_id": normalized_voice,
            "rights_statement": rights_statement,
            "bindings": [
                {
                    "asset_id": binding.asset_id,
                    "asset_version": binding.asset_version,
                    "asset_sha256": binding.asset_sha256,
                    "role": binding.role.value,
                    "view_label": binding.view_label,
                }
                for binding in bindings
            ],
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return cls(
            id=version_id,
            entity_id=entity.id,
            owner_id=entity.owner_id,
            version_number=version_number,
            kind=kind,
            status=LibraryVersionStatus.DRAFT,
            label=normalized_label,
            notes=notes,
            invariants=invariants,
            state_notes=state_notes,
            voice_profile_id=normalized_voice,
            rights_statement=rights_statement,
            bindings=bindings,
            fingerprint=fingerprint,
            created_at=now,
        )

    def approve(self, *, now: datetime) -> LibraryVersion:
        if self.status is not LibraryVersionStatus.DRAFT:
            raise LibraryVersionStateError("only draft library versions can be approved")
        return replace(self, status=LibraryVersionStatus.APPROVED, approved_at=now)


@dataclass(frozen=True, slots=True)
class FilmBiblePin:
    entity_id: str
    library_version_id: str
    library_version_number: int
    version_kind: LibraryVersionKind
    version_fingerprint: str
    role: FilmBiblePinRole

    def __post_init__(self) -> None:
        _require_non_empty(self.entity_id, "library entity id")
        _require_non_empty(self.library_version_id, "library version id")
        if self.library_version_number < 1:
            raise DomainValidationError("pinned library version number must be positive")
        if _PIN_ROLE_VERSION_KIND[self.role] is not self.version_kind:
            raise DomainValidationError("film-bible role is incompatible with the library version")
        if len(self.version_fingerprint) != 64 or any(
            character not in "0123456789abcdef" for character in self.version_fingerprint
        ):
            raise DomainValidationError("pinned library fingerprint must be lowercase SHA-256")


def _pin_payload(pin: FilmBiblePin) -> dict[str, object]:
    return {
        "entity_id": pin.entity_id,
        "library_version_id": pin.library_version_id,
        "library_version_number": pin.library_version_number,
        "version_kind": pin.version_kind.value,
        "version_fingerprint": pin.version_fingerprint,
        "role": pin.role.value,
    }


@dataclass(frozen=True, slots=True)
class FilmBibleSnapshot:
    id: str
    project_id: str
    owner_id: str
    revision: int
    status: FilmBibleStatus
    pins: tuple[FilmBiblePin, ...]
    fingerprint: str
    created_at: datetime
    approved_at: datetime | None = None

    def __post_init__(self) -> None:
        for value, field in (
            (self.id, "film-bible snapshot id"),
            (self.project_id, "project id"),
            (self.owner_id, "owner id"),
        ):
            _require_non_empty(value, field)
        if self.revision < 1:
            raise DomainValidationError("film-bible revision must be positive")
        if not self.pins:
            raise DomainValidationError("film-bible snapshots require at least one pin")
        keys = [(pin.entity_id, pin.role) for pin in self.pins]
        if len(keys) != len(set(keys)):
            raise DomainValidationError("an entity role may be pinned only once per snapshot")
        if len(self.fingerprint) != 64 or any(
            character not in "0123456789abcdef" for character in self.fingerprint
        ):
            raise DomainValidationError("film-bible fingerprint must be lowercase SHA-256")
        _require_utc_aware(self.created_at, "created_at")
        if (self.status is FilmBibleStatus.APPROVED) != (self.approved_at is not None):
            raise DomainValidationError("film-bible approval state and timestamp must match")
        if self.approved_at is not None:
            _require_utc_aware(self.approved_at, "approved_at")
            if self.approved_at < self.created_at:
                raise DomainValidationError("approved_at cannot precede created_at")

    @classmethod
    def create(
        cls,
        *,
        snapshot_id: str,
        project_id: str,
        owner_id: str,
        revision: int,
        pins: tuple[FilmBiblePin, ...],
        now: datetime,
    ) -> FilmBibleSnapshot:
        payload = {
            "project_id": project_id,
            "revision": revision,
            "pins": [_pin_payload(pin) for pin in pins],
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return cls(
            id=snapshot_id,
            project_id=project_id,
            owner_id=owner_id,
            revision=revision,
            status=FilmBibleStatus.DRAFT,
            pins=pins,
            fingerprint=fingerprint,
            created_at=now,
        )

    def approve(self, *, now: datetime) -> FilmBibleSnapshot:
        if self.status is not FilmBibleStatus.DRAFT:
            raise LibraryVersionStateError("only draft film-bible snapshots can be approved")
        return replace(self, status=FilmBibleStatus.APPROVED, approved_at=now)


@dataclass(frozen=True, slots=True)
class FilmBibleResolutionCandidate:
    entity_id: str
    display_name: str
    entity_kind: LibraryEntityKind
    pins: tuple[FilmBiblePin, ...]


@dataclass(frozen=True, slots=True)
class FilmBibleNameResolution:
    mention: str
    status: NameResolutionStatus
    candidates: tuple[FilmBibleResolutionCandidate, ...]

    def __post_init__(self) -> None:
        normalize_display_text(self.mention, field="mention")
        if self.status is NameResolutionStatus.RESOLVED and len(self.candidates) != 1:
            raise DomainValidationError("resolved names require exactly one candidate")
        if self.status is NameResolutionStatus.AMBIGUOUS and len(self.candidates) < 2:
            raise DomainValidationError("ambiguous names require multiple candidates")
        if self.status is NameResolutionStatus.UNRESOLVED and self.candidates:
            raise DomainValidationError("unresolved names must not include candidates")


def resolve_film_bible_name(
    snapshot: FilmBibleSnapshot,
    entities: tuple[LibraryEntity, ...],
    mention: str,
    *,
    kind: LibraryEntityKind | None = None,
) -> FilmBibleNameResolution:
    normalized = normalize_display_text(mention, field="mention")
    lookup = normalized[1:].strip() if normalized.startswith("@") else normalized
    lookup_key = canonical_name(lookup)
    if not lookup_key:
        raise DomainValidationError("mention must include a name after @")
    pins_by_entity: dict[str, list[FilmBiblePin]] = {}
    for pin in snapshot.pins:
        pins_by_entity.setdefault(pin.entity_id, []).append(pin)
    candidates = tuple(
        FilmBibleResolutionCandidate(
            entity_id=entity.id,
            display_name=entity.display_name,
            entity_kind=entity.kind,
            pins=tuple(pins_by_entity[entity.id]),
        )
        for entity in entities
        if entity.id in pins_by_entity
        and (kind is None or entity.kind is kind)
        and any(
            canonical_name(candidate) == lookup_key
            for candidate in (entity.display_name, *entity.aliases)
        )
    )
    status = (
        NameResolutionStatus.UNRESOLVED
        if not candidates
        else (
            NameResolutionStatus.RESOLVED
            if len(candidates) == 1
            else NameResolutionStatus.AMBIGUOUS
        )
    )
    return FilmBibleNameResolution(mention=normalized, status=status, candidates=candidates)


@dataclass(frozen=True, slots=True)
class ShotBindingRevision:
    id: str
    project_id: str
    owner_id: str
    shot_id: str
    shot_version: int
    revision: int
    film_bible_snapshot_id: str
    bindings: tuple[FilmBiblePin, ...]
    fingerprint: str
    created_at: datetime

    def __post_init__(self) -> None:
        for value, field in (
            (self.id, "shot-binding revision id"),
            (self.project_id, "project id"),
            (self.owner_id, "owner id"),
            (self.shot_id, "shot id"),
            (self.film_bible_snapshot_id, "film-bible snapshot id"),
        ):
            _require_non_empty(value, field)
        if self.shot_version < 1 or self.revision < 1:
            raise DomainValidationError("shot and binding revisions must be positive")
        if not self.bindings:
            raise DomainValidationError("shot-binding revisions require at least one binding")
        keys = [(binding.entity_id, binding.role) for binding in self.bindings]
        if len(keys) != len(set(keys)):
            raise DomainValidationError("a shot may bind an entity role only once")
        if len(self.fingerprint) != 64 or any(
            character not in "0123456789abcdef" for character in self.fingerprint
        ):
            raise DomainValidationError("shot-binding fingerprint must be lowercase SHA-256")
        _require_utc_aware(self.created_at, "created_at")

    @classmethod
    def create(
        cls,
        *,
        binding_revision_id: str,
        project_id: str,
        owner_id: str,
        shot_id: str,
        shot_version: int,
        revision: int,
        film_bible_snapshot_id: str,
        bindings: tuple[FilmBiblePin, ...],
        now: datetime,
    ) -> ShotBindingRevision:
        payload = {
            "project_id": project_id,
            "shot_id": shot_id,
            "shot_version": shot_version,
            "revision": revision,
            "film_bible_snapshot_id": film_bible_snapshot_id,
            "bindings": [_pin_payload(binding) for binding in bindings],
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return cls(
            id=binding_revision_id,
            project_id=project_id,
            owner_id=owner_id,
            shot_id=shot_id,
            shot_version=shot_version,
            revision=revision,
            film_bible_snapshot_id=film_bible_snapshot_id,
            bindings=bindings,
            fingerprint=fingerprint,
            created_at=now,
        )


def _validate_sha256(value: str, field: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise DomainValidationError(f"{field} must be lowercase SHA-256")


MIN_REFERENCE_TRIM_MS = 250
MAX_REFERENCE_TRIM_MS = 30_000


@dataclass(frozen=True, slots=True)
class ReferenceVideoSourceSnapshot:
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
    library_entity_id: str | None = None
    library_version_id: str | None = None
    library_version_fingerprint: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.asset_id, "reference-video asset id")
        if self.asset_version < 1:
            raise DomainValidationError("reference-video asset version must be positive")
        _validate_sha256(self.asset_sha256, "reference-video asset checksum")
        if not self.media_type.startswith("video/"):
            raise DomainValidationError("reference-video media type must be video")
        _require_non_empty(self.inspector_revision, "reference-video inspector revision")
        if (
            min(
                self.duration_ms,
                self.width,
                self.height,
                self.frame_rate_numerator,
                self.frame_rate_denominator,
            )
            <= 0
        ):
            raise DomainValidationError("reference-video measured metadata must be positive")
        provenance = (
            self.library_entity_id,
            self.library_version_id,
            self.library_version_fingerprint,
        )
        if self.scope is AssetScope.LIBRARY:
            if any(value is None for value in provenance):
                raise DomainValidationError("library reference videos require exact provenance")
            assert self.library_entity_id is not None
            assert self.library_version_id is not None
            assert self.library_version_fingerprint is not None
            _require_non_empty(self.library_entity_id, "library entity id")
            _require_non_empty(self.library_version_id, "library version id")
            _validate_sha256(self.library_version_fingerprint, "library version fingerprint")
        elif any(value is not None for value in provenance):
            raise DomainValidationError("project reference videos cannot claim library provenance")


def _reference_video_source_payload(
    source: ReferenceVideoSourceSnapshot,
) -> dict[str, object]:
    return {
        "asset_id": source.asset_id,
        "asset_version": source.asset_version,
        "asset_sha256": source.asset_sha256,
        "media_type": source.media_type,
        "scope": source.scope.value,
        "inspector_revision": source.inspector_revision,
        "duration_ms": source.duration_ms,
        "width": source.width,
        "height": source.height,
        "frame_rate_numerator": source.frame_rate_numerator,
        "frame_rate_denominator": source.frame_rate_denominator,
        "library_entity_id": source.library_entity_id,
        "library_version_id": source.library_version_id,
        "library_version_fingerprint": source.library_version_fingerprint,
    }


@dataclass(frozen=True, slots=True)
class ReferenceVideoGuidance:
    id: str
    project_id: str
    owner_id: str
    shot_id: str
    shot_version: int
    shot_binding_revision_id: str
    revision: int
    purpose: ReferenceVideoPurpose
    source: ReferenceVideoSourceSnapshot
    trim_start_ms: int
    trim_end_ms: int
    guidance_notes: str
    status: ReferenceGuidanceStatus
    fingerprint: str
    created_at: datetime
    approved_at: datetime | None = None

    def __post_init__(self) -> None:
        for value, field in (
            (self.id, "reference-guidance id"),
            (self.project_id, "project id"),
            (self.owner_id, "owner id"),
            (self.shot_id, "shot id"),
            (self.shot_binding_revision_id, "shot-binding revision id"),
        ):
            _require_non_empty(value, field)
        if self.shot_version < 1 or self.revision < 1:
            raise DomainValidationError("shot and reference-guidance revisions must be positive")
        if self.trim_start_ms < 0 or self.trim_end_ms > self.source.duration_ms:
            raise DomainValidationError("reference-video trim must be inside measured duration")
        trim_duration = self.trim_end_ms - self.trim_start_ms
        if not MIN_REFERENCE_TRIM_MS <= trim_duration <= MAX_REFERENCE_TRIM_MS:
            raise DomainValidationError(
                "reference-video trim must be between 250 and 30000 milliseconds"
            )
        normalized_notes = unicodedata.normalize("NFC", self.guidance_notes)
        if normalized_notes != self.guidance_notes or len(self.guidance_notes) > 2_000:
            raise DomainValidationError(
                "reference guidance notes must be NFC-normalized and at most 2000 characters"
            )
        if "\x00" in self.guidance_notes:
            raise DomainValidationError("reference guidance notes must not contain null characters")
        _validate_sha256(self.fingerprint, "reference-guidance fingerprint")
        _require_utc_aware(self.created_at, "created_at")
        if self.status is ReferenceGuidanceStatus.APPROVED and self.approved_at is None:
            raise DomainValidationError("approved reference guidance requires approved_at")
        if self.status is ReferenceGuidanceStatus.DRAFT and self.approved_at is not None:
            raise DomainValidationError("draft reference guidance cannot have approved_at")
        if self.approved_at is not None:
            _require_utc_aware(self.approved_at, "approved_at")
            if self.approved_at < self.created_at:
                raise DomainValidationError("approved_at cannot precede created_at")

    @classmethod
    def create(
        cls,
        *,
        guidance_id: str,
        project_id: str,
        owner_id: str,
        shot_id: str,
        shot_version: int,
        shot_binding_revision_id: str,
        revision: int,
        purpose: ReferenceVideoPurpose,
        source: ReferenceVideoSourceSnapshot,
        trim_start_ms: int,
        trim_end_ms: int,
        guidance_notes: str,
        now: datetime,
    ) -> ReferenceVideoGuidance:
        normalized_notes = unicodedata.normalize("NFC", guidance_notes)
        payload = {
            "project_id": project_id,
            "shot_id": shot_id,
            "shot_version": shot_version,
            "shot_binding_revision_id": shot_binding_revision_id,
            "revision": revision,
            "purpose": purpose.value,
            "source": _reference_video_source_payload(source),
            "trim_start_ms": trim_start_ms,
            "trim_end_ms": trim_end_ms,
            "guidance_notes": normalized_notes,
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return cls(
            id=guidance_id,
            project_id=project_id,
            owner_id=owner_id,
            shot_id=shot_id,
            shot_version=shot_version,
            shot_binding_revision_id=shot_binding_revision_id,
            revision=revision,
            purpose=purpose,
            source=source,
            trim_start_ms=trim_start_ms,
            trim_end_ms=trim_end_ms,
            guidance_notes=normalized_notes,
            status=ReferenceGuidanceStatus.DRAFT,
            fingerprint=fingerprint,
            created_at=now,
        )

    def approve(self, *, now: datetime) -> ReferenceVideoGuidance:
        if self.status is not ReferenceGuidanceStatus.DRAFT:
            raise DomainValidationError("only draft reference guidance can be approved")
        return replace(self, status=ReferenceGuidanceStatus.APPROVED, approved_at=now)


@dataclass(frozen=True, slots=True)
class CompositionAssetSnapshot:
    asset_id: str
    asset_version: int
    asset_sha256: str
    scope: AssetScope
    library_entity_id: str | None = None
    library_version_id: str | None = None
    library_version_fingerprint: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.asset_id, "composition asset id")
        if self.asset_version < 1:
            raise DomainValidationError("composition asset version must be positive")
        _validate_sha256(self.asset_sha256, "composition asset checksum")
        provenance = (
            self.library_entity_id,
            self.library_version_id,
            self.library_version_fingerprint,
        )
        if self.scope is AssetScope.LIBRARY:
            if any(value is None for value in provenance):
                raise DomainValidationError("library composition assets require exact provenance")
            assert self.library_entity_id is not None
            assert self.library_version_id is not None
            assert self.library_version_fingerprint is not None
            _require_non_empty(self.library_entity_id, "library entity id")
            _require_non_empty(self.library_version_id, "library version id")
            _validate_sha256(self.library_version_fingerprint, "library version fingerprint")
        elif any(value is not None for value in provenance):
            raise DomainValidationError(
                "project composition assets cannot claim library provenance"
            )


@dataclass(frozen=True, slots=True)
class SourceCrop:
    x: int
    y: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.x < 0 or self.y < 0:
            raise DomainValidationError("source crop origin must be non-negative")
        if self.width < 1 or self.height < 1:
            raise DomainValidationError("source crop dimensions must be positive")


@dataclass(frozen=True, slots=True)
class LayerTransform:
    x: int
    y: int
    width: int
    height: int
    rotation_millidegrees: int
    opacity_basis_points: int
    fit: CompositionFit
    crop: SourceCrop | None = None

    def __post_init__(self) -> None:
        if not -16_384 <= self.x <= 16_384 or not -16_384 <= self.y <= 16_384:
            raise DomainValidationError("layer position is outside the supported canvas range")
        if not 1 <= self.width <= 8_192 or not 1 <= self.height <= 8_192:
            raise DomainValidationError("layer dimensions are outside the supported range")
        if not -360_000 <= self.rotation_millidegrees <= 360_000:
            raise DomainValidationError("layer rotation must be between -360 and 360 degrees")
        if not 0 <= self.opacity_basis_points <= 10_000:
            raise DomainValidationError("layer opacity must be between 0 and 10000 basis points")


@dataclass(frozen=True, slots=True)
class StartingFrameLayer:
    role: CompositionLayerRole
    source: CompositionAssetSnapshot
    transform: LayerTransform
    mask: CompositionAssetSnapshot | None = None


def _asset_snapshot_payload(snapshot: CompositionAssetSnapshot) -> dict[str, object]:
    return {
        "asset_id": snapshot.asset_id,
        "asset_version": snapshot.asset_version,
        "asset_sha256": snapshot.asset_sha256,
        "scope": snapshot.scope.value,
        "library_entity_id": snapshot.library_entity_id,
        "library_version_id": snapshot.library_version_id,
        "library_version_fingerprint": snapshot.library_version_fingerprint,
    }


def _layer_payload(layer: StartingFrameLayer) -> dict[str, object]:
    crop = layer.transform.crop
    return {
        "role": layer.role.value,
        "source": _asset_snapshot_payload(layer.source),
        "mask": _asset_snapshot_payload(layer.mask) if layer.mask is not None else None,
        "transform": {
            "x": layer.transform.x,
            "y": layer.transform.y,
            "width": layer.transform.width,
            "height": layer.transform.height,
            "rotation_millidegrees": layer.transform.rotation_millidegrees,
            "opacity_basis_points": layer.transform.opacity_basis_points,
            "fit": layer.transform.fit.value,
            "crop": (
                None
                if crop is None
                else {"x": crop.x, "y": crop.y, "width": crop.width, "height": crop.height}
            ),
        },
    }


@dataclass(frozen=True, slots=True)
class StartingFrameComposition:
    id: str
    project_id: str
    owner_id: str
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
    layers: tuple[StartingFrameLayer, ...]
    fingerprint: str
    created_at: datetime
    rendered_asset_id: str | None = None
    rendered_asset_version: int | None = None
    rendered_sha256: str | None = None
    renderer_revision: str | None = None
    rendered_at: datetime | None = None
    approved_at: datetime | None = None

    def __post_init__(self) -> None:
        for value, field in (
            (self.id, "starting-frame composition id"),
            (self.project_id, "project id"),
            (self.owner_id, "owner id"),
            (self.shot_id, "shot id"),
            (self.shot_binding_revision_id, "shot-binding revision id"),
        ):
            _require_non_empty(value, field)
        if self.shot_version < 1 or self.revision < 1:
            raise DomainValidationError("shot and composition revisions must be positive")
        if not 64 <= self.canvas_width <= 4096 or not 64 <= self.canvas_height <= 4096:
            raise DomainValidationError("composition canvas dimensions must be between 64 and 4096")
        if self.canvas_width * self.canvas_height > 16_777_216:
            raise DomainValidationError("composition canvas exceeds the maximum pixel count")
        if (
            len(self.background_rgba) != 9
            or self.background_rgba[0] != "#"
            or any(
                character not in "0123456789abcdefABCDEF" for character in self.background_rgba[1:]
            )
        ):
            raise DomainValidationError("composition background must be #RRGGBBAA")
        if not self.layers or len(self.layers) > 32:
            raise DomainValidationError("compositions require between 1 and 32 layers")
        if self.mode is StartingFrameMode.COMPOSED_UPLOAD and (
            len(self.layers) != 1 or self.layers[0].role is not CompositionLayerRole.STARTING_FRAME
        ):
            raise DomainValidationError("composed-upload mode requires one starting-frame layer")
        if self.mode is StartingFrameMode.LAYERED:
            if any(layer.role is CompositionLayerRole.STARTING_FRAME for layer in self.layers):
                raise DomainValidationError(
                    "starting-frame layers belong only to composed-upload mode"
                )
            if not any(layer.role is CompositionLayerRole.BACKGROUND for layer in self.layers):
                raise DomainValidationError("layered compositions require a background layer")
        for value, field in (
            (self.framing_notes, "framing notes"),
            (self.pose_notes, "pose notes"),
            (self.action_notes, "action notes"),
            (self.lighting_notes, "lighting notes"),
        ):
            if len(value) > 2_000 or "\x00" in value:
                raise DomainValidationError(f"{field} must contain at most 2000 safe characters")
        if self.visible_speaker_entity_id is not None:
            _require_non_empty(self.visible_speaker_entity_id, "visible speaker entity id")
        _validate_sha256(self.fingerprint, "composition fingerprint")
        _require_utc_aware(self.created_at, "created_at")
        output = (
            self.rendered_asset_id,
            self.rendered_asset_version,
            self.rendered_sha256,
            self.renderer_revision,
            self.rendered_at,
        )
        has_output = all(value is not None for value in output)
        if any(value is not None for value in output) and not has_output:
            raise DomainValidationError("rendered composition metadata must be complete")
        if self.status is StartingFrameStatus.DRAFT and (
            has_output or self.approved_at is not None
        ):
            raise DomainValidationError("draft compositions cannot have rendered or approved data")
        if self.status is not StartingFrameStatus.DRAFT and not has_output:
            raise DomainValidationError("rendered compositions require output metadata")
        if self.status is StartingFrameStatus.APPROVED and self.approved_at is None:
            raise DomainValidationError("approved compositions require an approval timestamp")
        if self.status is not StartingFrameStatus.APPROVED and self.approved_at is not None:
            raise DomainValidationError("only approved compositions may have an approval timestamp")
        if self.rendered_sha256 is not None:
            _validate_sha256(self.rendered_sha256, "rendered composition checksum")
        if self.rendered_at is not None:
            _require_utc_aware(self.rendered_at, "rendered_at")
        if self.approved_at is not None:
            _require_utc_aware(self.approved_at, "approved_at")

    @classmethod
    def create(
        cls,
        *,
        composition_id: str,
        project_id: str,
        owner_id: str,
        shot_id: str,
        shot_version: int,
        shot_binding_revision_id: str,
        revision: int,
        mode: StartingFrameMode,
        canvas_width: int,
        canvas_height: int,
        background_rgba: str,
        output_rights: RightsDeclaration,
        framing_notes: str,
        pose_notes: str,
        action_notes: str,
        lighting_notes: str,
        visible_speaker_entity_id: str | None,
        layers: tuple[StartingFrameLayer, ...],
        now: datetime,
    ) -> StartingFrameComposition:
        payload = {
            "project_id": project_id,
            "shot_id": shot_id,
            "shot_version": shot_version,
            "shot_binding_revision_id": shot_binding_revision_id,
            "revision": revision,
            "mode": mode.value,
            "canvas_width": canvas_width,
            "canvas_height": canvas_height,
            "background_rgba": background_rgba.lower(),
            "output_rights": output_rights.value,
            "framing_notes": framing_notes,
            "pose_notes": pose_notes,
            "action_notes": action_notes,
            "lighting_notes": lighting_notes,
            "visible_speaker_entity_id": visible_speaker_entity_id,
            "layers": [_layer_payload(layer) for layer in layers],
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return cls(
            id=composition_id,
            project_id=project_id,
            owner_id=owner_id,
            shot_id=shot_id,
            shot_version=shot_version,
            shot_binding_revision_id=shot_binding_revision_id,
            revision=revision,
            mode=mode,
            status=StartingFrameStatus.DRAFT,
            canvas_width=canvas_width,
            canvas_height=canvas_height,
            background_rgba=background_rgba.lower(),
            output_rights=output_rights,
            framing_notes=framing_notes,
            pose_notes=pose_notes,
            action_notes=action_notes,
            lighting_notes=lighting_notes,
            visible_speaker_entity_id=visible_speaker_entity_id,
            layers=layers,
            fingerprint=fingerprint,
            created_at=now,
        )

    def with_rendered_asset(
        self,
        *,
        asset_id: str,
        asset_version: int,
        asset_sha256: str,
        renderer_revision: str,
        now: datetime,
    ) -> StartingFrameComposition:
        if self.status is not StartingFrameStatus.DRAFT:
            raise LibraryVersionStateError("only draft compositions can be rendered")
        return replace(
            self,
            status=StartingFrameStatus.RENDERED,
            rendered_asset_id=asset_id,
            rendered_asset_version=asset_version,
            rendered_sha256=asset_sha256,
            renderer_revision=renderer_revision,
            rendered_at=now,
        )

    def approve(self, *, now: datetime) -> StartingFrameComposition:
        if self.status is not StartingFrameStatus.RENDERED:
            raise LibraryVersionStateError("only rendered compositions can be approved")
        return replace(self, status=StartingFrameStatus.APPROVED, approved_at=now)


class LibraryMetadataVersionError(RuntimeError):
    """Raised when library display metadata is edited from a stale revision."""


class LibraryVersionStateError(RuntimeError):
    """Raised when an immutable library-version state transition is invalid."""
