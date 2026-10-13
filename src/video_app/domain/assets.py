"""Owner-scoped immutable media asset records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from video_app.domain.models import DomainValidationError, _require_non_empty, _require_utc_aware


class AssetKind(str, Enum):
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"


class RightsDeclaration(str, Enum):
    OWNED = "owned"
    LICENSED = "licensed"
    PERMISSIONED = "permissioned"
    PUBLIC_DOMAIN = "public_domain"


class AssetState(str, Enum):
    READY = "ready"
    INSPECTED = "inspected"


class AssetScope(str, Enum):
    """Explicit authorization scope for an uploaded asset."""

    PROJECT = "project"
    LIBRARY = "library"


@dataclass(frozen=True, slots=True)
class MediaMetadata:
    format_name: str
    duration_ms: int
    width: int | None = None
    height: int | None = None
    frame_rate_numerator: int | None = None
    frame_rate_denominator: int | None = None
    sample_rate: int | None = None
    channels: int | None = None
    sample_count: int | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.format_name, "format name")
        if self.duration_ms <= 0:
            raise DomainValidationError("measured duration must be positive")
        video_values = (
            self.width,
            self.height,
            self.frame_rate_numerator,
            self.frame_rate_denominator,
        )
        audio_values = (self.sample_rate, self.channels, self.sample_count)
        if any(value is not None for value in video_values) and not all(
            value is not None and value > 0 for value in video_values
        ):
            raise DomainValidationError("video metadata must be complete and positive")
        if any(value is not None for value in audio_values) and not all(
            value is not None and value > 0 for value in audio_values
        ):
            raise DomainValidationError("audio metadata must be complete and positive")
        if all(value is None for value in video_values + audio_values):
            raise DomainValidationError("media metadata must contain an audio or video stream")


@dataclass(frozen=True, slots=True)
class MediaAsset:
    id: str
    project_id: str | None
    owner_id: str
    version: int
    kind: AssetKind
    state: AssetState
    original_filename: str
    media_type: str
    storage_key: str
    size_bytes: int
    sha256: str
    rights: RightsDeclaration
    created_at: datetime
    metadata: MediaMetadata | None = None
    inspector_revision: str | None = None
    inspected_at: datetime | None = None
    scope: AssetScope = AssetScope.PROJECT

    def __post_init__(self) -> None:
        for value, field in ((self.id, "asset id"), (self.owner_id, "owner id")):
            _require_non_empty(value, field)
        if self.scope is AssetScope.PROJECT:
            if self.project_id is None:
                raise DomainValidationError("project assets require a project id")
            _require_non_empty(self.project_id, "project id")
        elif self.project_id is not None:
            raise DomainValidationError("library assets must not have a project id")
        if self.version < 1:
            raise DomainValidationError("asset version must be positive")
        if not self.original_filename or len(self.original_filename) > 255:
            raise DomainValidationError("asset filename must contain between 1 and 255 characters")
        if any(character in self.original_filename for character in ("/", "\\", "\0")):
            raise DomainValidationError("asset filename must not contain path separators")
        _require_non_empty(self.media_type, "media type")
        _require_non_empty(self.storage_key, "storage key")
        if self.size_bytes <= 0:
            raise DomainValidationError("asset size must be positive")
        if len(self.sha256) != 64 or any(c not in "0123456789abcdef" for c in self.sha256):
            raise DomainValidationError("asset checksum must be lowercase SHA-256")
        _require_utc_aware(self.created_at, "created_at")
        inspected = self.metadata is not None
        if inspected != (self.inspector_revision is not None and self.inspected_at is not None):
            raise DomainValidationError("inspection fields must be present together")
        if self.state is AssetState.INSPECTED and not inspected:
            raise DomainValidationError("inspected assets require measured metadata")
        if self.state is AssetState.READY and inspected:
            raise DomainValidationError("ready assets must not contain inspection metadata")
        if self.inspected_at is not None:
            _require_utc_aware(self.inspected_at, "inspected_at")
            if self.inspected_at < self.created_at:
                raise DomainValidationError("inspected_at cannot precede created_at")

    def with_inspection(
        self, metadata: MediaMetadata, *, inspector_revision: str, inspected_at: datetime
    ) -> MediaAsset:
        from dataclasses import replace

        _require_non_empty(inspector_revision, "inspector revision")
        return replace(
            self,
            version=self.version + 1,
            state=AssetState.INSPECTED,
            metadata=metadata,
            inspector_revision=inspector_revision,
            inspected_at=inspected_at,
        )
