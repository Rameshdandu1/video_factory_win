"""Immutable value objects implementing Generation Contract v1."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from pathlib import Path

MIN_SEED = -(2**63)
MAX_SEED = 2**63 - 1
SHA256_HEX_LENGTH = 64


class DomainValidationError(ValueError):
    """Raised when a value violates a stable domain contract."""


class GenerationMode(str, Enum):
    """Generation capabilities exposed by contract v1."""

    TEXT_TO_VIDEO = "text_to_video"
    IMAGE_TO_VIDEO = "image_to_video"
    ROUGH_CUT = "rough_cut"
    TIMELINE_RENDER = "timeline_render"


class ControlledVideoOperation(str, Enum):
    """Reference-driven operation whose semantics must remain explicit."""

    VACE_PERFORMANCE_TRANSFER = "vace_performance_transfer"
    ANIMATE_CHARACTER = "animate_character"
    ANIMATE_REPLACEMENT = "animate_replacement"


class ErrorCode(str, Enum):
    """Stable public failure codes from Generation Contract v1."""

    INVALID_REQUEST = "INVALID_REQUEST"
    UNSUPPORTED_MODEL = "UNSUPPORTED_MODEL"
    UNSUPPORTED_PARAMETERS = "UNSUPPORTED_PARAMETERS"
    QUEUE_FULL = "QUEUE_FULL"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    INSUFFICIENT_RESOURCES = "INSUFFICIENT_RESOURCES"
    GENERATION_FAILED = "GENERATION_FAILED"
    OUTPUT_WRITE_FAILED = "OUTPUT_WRITE_FAILED"
    JOB_NOT_FOUND = "JOB_NOT_FOUND"
    JOB_NOT_CANCELLABLE = "JOB_NOT_CANCELLABLE"
    PROJECT_NOT_FOUND = "PROJECT_NOT_FOUND"
    REVISION_CONFLICT = "REVISION_CONFLICT"
    ASSET_INVALID = "ASSET_INVALID"
    ASSET_TOO_LARGE = "ASSET_TOO_LARGE"
    ASSET_NOT_FOUND = "ASSET_NOT_FOUND"
    MEDIA_INSPECTION_FAILED = "MEDIA_INSPECTION_FAILED"
    MEDIA_INSPECTION_UNAVAILABLE = "MEDIA_INSPECTION_UNAVAILABLE"
    TIMELINE_NOT_FOUND = "TIMELINE_NOT_FOUND"
    FILM_SUBJECT_NOT_FOUND = "FILM_SUBJECT_NOT_FOUND"
    LIBRARY_ENTITY_NOT_FOUND = "LIBRARY_ENTITY_NOT_FOUND"
    LIBRARY_VERSION_NOT_FOUND = "LIBRARY_VERSION_NOT_FOUND"
    LIBRARY_REVISION_CONFLICT = "LIBRARY_REVISION_CONFLICT"
    FILM_BIBLE_NOT_FOUND = "FILM_BIBLE_NOT_FOUND"
    STARTING_FRAME_NOT_FOUND = "STARTING_FRAME_NOT_FOUND"
    STARTING_FRAME_RENDER_FAILED = "STARTING_FRAME_RENDER_FAILED"
    REFERENCE_GUIDANCE_NOT_FOUND = "REFERENCE_GUIDANCE_NOT_FOUND"
    IMAGE_GENERATION_NOT_FOUND = "IMAGE_GENERATION_NOT_FOUND"
    IMAGE_GENERATION_UNAVAILABLE = "IMAGE_GENERATION_UNAVAILABLE"
    CONSTRAINT_CONFLICT = "CONSTRAINT_CONFLICT"
    ROUGH_CUT_NOT_FOUND = "ROUGH_CUT_NOT_FOUND"
    TIMELINE_RENDER_NOT_FOUND = "TIMELINE_RENDER_NOT_FOUND"
    MEDIA_RENDER_UNAVAILABLE = "MEDIA_RENDER_UNAVAILABLE"
    MEDIA_RENDER_FAILED = "MEDIA_RENDER_FAILED"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    INTERNAL_ERROR = "INTERNAL_ERROR"


def _require_non_empty(value: str, field: str) -> None:
    if not value or value.isspace():
        raise DomainValidationError(f"{field} must not be empty")


def _require_utc_aware(value: datetime, field: str) -> None:
    offset = value.utcoffset()
    if value.tzinfo is None or offset is None:
        raise DomainValidationError(f"{field} must be timezone-aware")
    if offset.total_seconds() != 0:
        raise DomainValidationError(f"{field} must use UTC")


@dataclass(frozen=True, slots=True, order=True)
class Resolution:
    """A supported width and height pair."""

    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise DomainValidationError("resolution dimensions must be positive")


@dataclass(frozen=True, slots=True)
class ModelCapability:
    """Backend-neutral settings supported by one logical model."""

    model_id: str
    display_name: str
    modes: frozenset[GenerationMode]
    resolutions: frozenset[Resolution]
    frame_counts: frozenset[int]
    enabled: bool = True

    def __post_init__(self) -> None:
        _require_non_empty(self.model_id, "model_id")
        _require_non_empty(self.display_name, "display_name")
        if not self.modes:
            raise DomainValidationError("model capability must include a mode")
        if not self.resolutions:
            raise DomainValidationError("model capability must include a resolution")
        if not self.frame_counts or any(count <= 0 for count in self.frame_counts):
            raise DomainValidationError("frame counts must contain positive values")


@dataclass(frozen=True, slots=True)
class GenerationRequestDraft:
    """Validated-at-normalization request whose seed may be omitted."""

    prompt: str
    model: str
    width: int
    height: int
    frame_count: int
    seed: int | None = None
    mode: GenerationMode = GenerationMode.TEXT_TO_VIDEO


@dataclass(frozen=True, slots=True)
class ImageConditioning:
    """Immutable approved starting-frame manifest consumed by an I2V backend."""

    owner_id: str
    project_id: str
    shot_id: str
    shot_version: int
    composition_id: str
    composition_revision: int
    composition_fingerprint: str
    source_asset_id: str
    source_asset_version: int
    source_asset_sha256: str
    source_storage_key: str
    source_width: int
    source_height: int
    required_backend: str
    required_backend_revision: str
    manifest_fingerprint: str
    reference_video: ReferenceVideoConditioning | None = None

    def __post_init__(self) -> None:
        for value, field in (
            (self.owner_id, "conditioning owner id"),
            (self.project_id, "conditioning project id"),
            (self.shot_id, "conditioning shot id"),
            (self.composition_id, "conditioning composition id"),
            (self.source_asset_id, "conditioning source asset id"),
            (self.source_storage_key, "conditioning source storage key"),
            (self.required_backend, "conditioning backend"),
            (self.required_backend_revision, "conditioning backend revision"),
        ):
            _require_non_empty(value, field)
        if self.shot_version < 1 or self.composition_revision < 1:
            raise DomainValidationError("conditioning revisions must be positive")
        if self.source_asset_version < 1:
            raise DomainValidationError("conditioning source asset version must be positive")
        if self.source_width < 64 or self.source_height < 64:
            raise DomainValidationError("conditioning source dimensions are too small")
        for value, field in (
            (self.composition_fingerprint, "composition fingerprint"),
            (self.source_asset_sha256, "conditioning source checksum"),
            (self.manifest_fingerprint, "conditioning manifest fingerprint"),
        ):
            if len(value) != SHA256_HEX_LENGTH or any(
                character not in "0123456789abcdef" for character in value
            ):
                raise DomainValidationError(f"{field} must be lowercase SHA-256")


@dataclass(frozen=True, slots=True)
class ReferenceVideoConditioning:
    """Frozen approved guidance and the constraint decision sent to a backend."""

    guidance_id: str
    guidance_revision: int
    guidance_fingerprint: str
    purpose: str
    source_asset_id: str
    source_asset_version: int
    source_asset_sha256: str
    source_storage_key: str
    trim_start_ms: int
    trim_end_ms: int
    operation: ControlledVideoOperation
    preserve_environment: bool
    constraint_plan_fingerprint: str

    def __post_init__(self) -> None:
        for value, field in (
            (self.guidance_id, "reference guidance id"),
            (self.purpose, "reference guidance purpose"),
            (self.source_asset_id, "reference source asset id"),
            (self.source_storage_key, "reference source storage key"),
        ):
            _require_non_empty(value, field)
        if self.guidance_revision < 1 or self.source_asset_version < 1:
            raise DomainValidationError("reference guidance and asset revisions must be positive")
        if self.trim_start_ms < 0 or self.trim_end_ms <= self.trim_start_ms:
            raise DomainValidationError("reference-video trim must be a positive range")
        if self.purpose != "motion_performance":
            raise DomainValidationError("controlled video requires motion-performance guidance")
        if (
            self.operation is ControlledVideoOperation.VACE_PERFORMANCE_TRANSFER
        ) != self.preserve_environment:
            raise DomainValidationError(
                "environment preservation must match the controlled-video operation"
            )
        for value, field in (
            (self.guidance_fingerprint, "reference guidance fingerprint"),
            (self.source_asset_sha256, "reference source checksum"),
            (self.constraint_plan_fingerprint, "constraint plan fingerprint"),
        ):
            if len(value) != SHA256_HEX_LENGTH or any(
                character not in "0123456789abcdef" for character in value
            ):
                raise DomainValidationError(f"{field} must be lowercase SHA-256")


def _validate_sha256(value: str, field: str) -> None:
    if len(value) != SHA256_HEX_LENGTH or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise DomainValidationError(f"{field} must be lowercase SHA-256")


@dataclass(frozen=True, slots=True)
class RoughCutSource:
    """One exact approved media asset consumed by a rough-cut worker."""

    asset_id: str
    asset_version: int
    sha256: str
    storage_key: str

    def __post_init__(self) -> None:
        _require_non_empty(self.asset_id, "rough-cut asset id")
        _require_non_empty(self.storage_key, "rough-cut storage key")
        if self.asset_version < 1:
            raise DomainValidationError("rough-cut asset version must be positive")
        _validate_sha256(self.sha256, "rough-cut asset checksum")

    def payload(self) -> dict[str, object]:
        return {
            "asset_id": self.asset_id,
            "asset_version": self.asset_version,
            "sha256": self.sha256,
            "storage_key": self.storage_key,
        }


@dataclass(frozen=True, slots=True)
class RoughCutItem:
    """Frozen storyboard and dialogue for one independently replaceable film shot."""

    scene_id: str
    scene_version: int
    scene_fingerprint: str
    scene_position: int
    shot_id: str
    shot_version: int
    shot_fingerprint: str
    shot_position: int
    duration_ms: int
    storyboard: RoughCutSource
    dialogue: RoughCutSource

    def __post_init__(self) -> None:
        for value, field in (
            (self.scene_id, "rough-cut scene id"),
            (self.shot_id, "rough-cut shot id"),
        ):
            _require_non_empty(value, field)
        if self.scene_version < 1 or self.shot_version < 1:
            raise DomainValidationError("rough-cut creative revisions must be positive")
        if self.scene_position < 0 or self.shot_position < 0 or self.duration_ms <= 0:
            raise DomainValidationError("rough-cut item position and duration are invalid")
        _validate_sha256(self.scene_fingerprint, "rough-cut scene fingerprint")
        _validate_sha256(self.shot_fingerprint, "rough-cut shot fingerprint")

    def payload(self) -> dict[str, object]:
        return {
            "scene_id": self.scene_id,
            "scene_version": self.scene_version,
            "scene_fingerprint": self.scene_fingerprint,
            "scene_position": self.scene_position,
            "shot_id": self.shot_id,
            "shot_version": self.shot_version,
            "shot_fingerprint": self.shot_fingerprint,
            "shot_position": self.shot_position,
            "duration_ms": self.duration_ms,
            "storyboard": self.storyboard.payload(),
            "dialogue": self.dialogue.payload(),
        }


@dataclass(frozen=True, slots=True)
class RoughCutManifest:
    """Immutable current-edit manifest routed to one exact FFmpeg worker revision."""

    owner_id: str
    project_id: str
    workspace_fingerprint: str
    width: int
    height: int
    fps_numerator: int
    fps_denominator: int
    total_duration_ms: int
    required_backend: str
    required_backend_revision: str
    items: tuple[RoughCutItem, ...]
    manifest_fingerprint: str

    @classmethod
    def create(
        cls,
        *,
        owner_id: str,
        project_id: str,
        workspace_fingerprint: str,
        width: int,
        height: int,
        fps_numerator: int,
        fps_denominator: int,
        total_duration_ms: int,
        required_backend: str,
        required_backend_revision: str,
        items: tuple[RoughCutItem, ...],
    ) -> RoughCutManifest:
        payload: dict[str, object] = {
            "owner_id": owner_id,
            "project_id": project_id,
            "workspace_fingerprint": workspace_fingerprint,
            "width": width,
            "height": height,
            "fps_numerator": fps_numerator,
            "fps_denominator": fps_denominator,
            "total_duration_ms": total_duration_ms,
            "required_backend": required_backend,
            "required_backend_revision": required_backend_revision,
            "items": [item.payload() for item in items],
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return cls(
            owner_id=owner_id,
            project_id=project_id,
            workspace_fingerprint=workspace_fingerprint,
            width=width,
            height=height,
            fps_numerator=fps_numerator,
            fps_denominator=fps_denominator,
            total_duration_ms=total_duration_ms,
            required_backend=required_backend,
            required_backend_revision=required_backend_revision,
            items=items,
            manifest_fingerprint=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        )

    def __post_init__(self) -> None:
        for value, field in (
            (self.owner_id, "rough-cut owner id"),
            (self.project_id, "rough-cut project id"),
            (self.required_backend, "rough-cut backend"),
            (self.required_backend_revision, "rough-cut backend revision"),
        ):
            _require_non_empty(value, field)
        _validate_sha256(self.workspace_fingerprint, "rough-cut workspace fingerprint")
        if min(self.width, self.height, self.fps_numerator, self.fps_denominator) <= 0:
            raise DomainValidationError("rough-cut export settings must be positive")
        if not 1_000 <= self.total_duration_ms <= 3_600_000:
            raise DomainValidationError("rough-cut duration must be between 1 and 3600 seconds")
        if not self.items or len(self.items) > 500:
            raise DomainValidationError("rough cut must contain between 1 and 500 shots")
        if sum(item.duration_ms for item in self.items) != self.total_duration_ms:
            raise DomainValidationError("rough-cut items must fill the complete duration")
        ordering = tuple((item.scene_position, item.shot_position) for item in self.items)
        if ordering != tuple(sorted(ordering)) or len(set(ordering)) != len(ordering):
            raise DomainValidationError("rough-cut items must use unique ordered positions")
        if len({item.shot_id for item in self.items}) != len(self.items):
            raise DomainValidationError("rough-cut shot ids must be unique")
        _validate_sha256(self.manifest_fingerprint, "rough-cut manifest fingerprint")
        if self.compute_fingerprint() != self.manifest_fingerprint:
            raise DomainValidationError("rough-cut manifest fingerprint does not match")
        _ = self.frame_count

    @property
    def frame_count(self) -> int:
        numerator = self.total_duration_ms * self.fps_numerator
        denominator = 1_000 * self.fps_denominator
        if numerator % denominator != 0:
            raise DomainValidationError("rough-cut duration must resolve to a whole frame count")
        return numerator // denominator

    def payload(self) -> dict[str, object]:
        return {
            "owner_id": self.owner_id,
            "project_id": self.project_id,
            "workspace_fingerprint": self.workspace_fingerprint,
            "width": self.width,
            "height": self.height,
            "fps_numerator": self.fps_numerator,
            "fps_denominator": self.fps_denominator,
            "total_duration_ms": self.total_duration_ms,
            "required_backend": self.required_backend,
            "required_backend_revision": self.required_backend_revision,
            "items": [item.payload() for item in self.items],
        }

    def compute_fingerprint(self) -> str:
        canonical = json.dumps(
            self.payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class TimelineRenderSource:
    """One exact project asset consumed by a final timeline render."""

    asset_id: str
    asset_version: int
    sha256: str
    storage_key: str
    media_kind: str
    measured_duration_ms: int | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.asset_id, "timeline-render asset id")
        _require_non_empty(self.storage_key, "timeline-render storage key")
        if self.asset_version < 1:
            raise DomainValidationError("timeline-render asset version must be positive")
        if self.media_kind not in {"image", "audio", "video"}:
            raise DomainValidationError("timeline-render source kind is invalid")
        if self.media_kind == "image":
            if self.measured_duration_ms is not None:
                raise DomainValidationError("timeline-render images cannot have a duration")
        elif self.measured_duration_ms is None or self.measured_duration_ms <= 0:
            raise DomainValidationError("timeline-render media requires measured duration")
        _validate_sha256(self.sha256, "timeline-render asset checksum")

    def payload(self) -> dict[str, object]:
        return {
            "asset_id": self.asset_id,
            "asset_version": self.asset_version,
            "sha256": self.sha256,
            "storage_key": self.storage_key,
            "media_kind": self.media_kind,
            "measured_duration_ms": self.measured_duration_ms,
        }


@dataclass(frozen=True, slots=True)
class TimelineRenderItem:
    """One frozen visual or audio item from an approved timeline."""

    kind: str
    start_ms: int
    duration_ms: int
    layer: int
    source: TimelineRenderSource | None = None
    text: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in {"video", "image", "audio", "title_card"}:
            raise DomainValidationError("timeline-render item kind is invalid")
        if self.start_ms < 0 or self.duration_ms <= 0 or not 0 <= self.layer <= 20:
            raise DomainValidationError("timeline-render item timing or layer is invalid")
        if self.kind == "title_card":
            if self.source is not None or self.text is None or not self.text.strip():
                raise DomainValidationError("timeline-render title cards require only text")
        elif self.source is None or self.text is not None or self.source.media_kind != self.kind:
            raise DomainValidationError("timeline-render media item source is invalid")
        if self.text is not None and len(self.text) > 500:
            raise DomainValidationError("timeline-render title text is too long")

    def payload(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "start_ms": self.start_ms,
            "duration_ms": self.duration_ms,
            "layer": self.layer,
            "source": None if self.source is None else self.source.payload(),
            "text": self.text.strip() if self.text is not None else None,
        }


@dataclass(frozen=True, slots=True)
class TimelineRenderCaption:
    start_ms: int
    end_ms: int
    text: str

    def __post_init__(self) -> None:
        if self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise DomainValidationError("timeline-render caption timing is invalid")
        if not self.text.strip() or len(self.text) > 500:
            raise DomainValidationError("timeline-render caption text is invalid")

    def payload(self) -> dict[str, object]:
        return {"start_ms": self.start_ms, "end_ms": self.end_ms, "text": self.text.strip()}


@dataclass(frozen=True, slots=True)
class TimelineRenderManifest:
    """Immutable approved-timeline manifest routed to one exact media worker."""

    owner_id: str
    project_id: str
    timeline_id: str
    timeline_revision: int
    timeline_fingerprint: str
    width: int
    height: int
    fps_numerator: int
    fps_denominator: int
    total_duration_ms: int
    required_backend: str
    required_backend_revision: str
    items: tuple[TimelineRenderItem, ...]
    captions: tuple[TimelineRenderCaption, ...]
    manifest_fingerprint: str

    @classmethod
    def create(
        cls,
        *,
        owner_id: str,
        project_id: str,
        timeline_id: str,
        timeline_revision: int,
        timeline_fingerprint: str,
        width: int,
        height: int,
        fps_numerator: int,
        fps_denominator: int,
        total_duration_ms: int,
        required_backend: str,
        required_backend_revision: str,
        items: tuple[TimelineRenderItem, ...],
        captions: tuple[TimelineRenderCaption, ...],
    ) -> TimelineRenderManifest:
        partial = cls(
            owner_id=owner_id,
            project_id=project_id,
            timeline_id=timeline_id,
            timeline_revision=timeline_revision,
            timeline_fingerprint=timeline_fingerprint,
            width=width,
            height=height,
            fps_numerator=fps_numerator,
            fps_denominator=fps_denominator,
            total_duration_ms=total_duration_ms,
            required_backend=required_backend,
            required_backend_revision=required_backend_revision,
            items=items,
            captions=captions,
            manifest_fingerprint="0" * SHA256_HEX_LENGTH,
        )
        return replace(partial, manifest_fingerprint=partial.compute_fingerprint())

    def __post_init__(self) -> None:
        for value, field in (
            (self.owner_id, "timeline-render owner id"),
            (self.project_id, "timeline-render project id"),
            (self.timeline_id, "timeline-render timeline id"),
            (self.required_backend, "timeline-render backend"),
            (self.required_backend_revision, "timeline-render backend revision"),
        ):
            _require_non_empty(value, field)
        if self.timeline_revision < 1:
            raise DomainValidationError("timeline-render revision must be positive")
        _validate_sha256(self.timeline_fingerprint, "timeline fingerprint")
        if min(self.width, self.height, self.fps_numerator, self.fps_denominator) <= 0:
            raise DomainValidationError("timeline-render export settings must be positive")
        if not 1_000 <= self.total_duration_ms <= 3_600_000:
            raise DomainValidationError(
                "timeline-render duration must be between 1 and 3600 seconds"
            )
        if not self.items or len(self.items) > 532 or len(self.captions) > 2_000:
            raise DomainValidationError("timeline render contains an invalid item count")
        visual = tuple(item for item in self.items if item.kind != "audio")
        audio = tuple(item for item in self.items if item.kind == "audio")
        if not visual or len(audio) > 32:
            raise DomainValidationError(
                "timeline render requires visuals and at most 32 audio items"
            )
        expected_start = 0
        for item in visual:
            if item.layer != 0 or item.start_ms != expected_start:
                raise DomainValidationError(
                    "timeline-render visuals must be contiguous on layer zero"
                )
            if (item.duration_ms * self.fps_numerator) % (1_000 * self.fps_denominator):
                raise DomainValidationError(
                    "timeline-render visual durations must resolve to whole frames"
                )
            expected_start += item.duration_ms
        if expected_start != self.total_duration_ms:
            raise DomainValidationError("timeline-render visuals must fill the complete duration")
        if any(item.start_ms + item.duration_ms > self.total_duration_ms for item in audio):
            raise DomainValidationError("timeline-render audio exceeds the complete duration")
        if any(item.end_ms > self.total_duration_ms for item in self.captions):
            raise DomainValidationError("timeline-render caption exceeds the complete duration")
        _validate_sha256(self.manifest_fingerprint, "timeline-render manifest fingerprint")
        if (
            self.manifest_fingerprint != "0" * SHA256_HEX_LENGTH
            and self.compute_fingerprint() != self.manifest_fingerprint
        ):
            raise DomainValidationError("timeline-render manifest fingerprint does not match")
        _ = self.frame_count

    @property
    def frame_count(self) -> int:
        numerator = self.total_duration_ms * self.fps_numerator
        denominator = 1_000 * self.fps_denominator
        if numerator % denominator != 0:
            raise DomainValidationError("timeline-render duration must resolve to whole frames")
        return numerator // denominator

    def payload(self) -> dict[str, object]:
        return {
            "owner_id": self.owner_id,
            "project_id": self.project_id,
            "timeline_id": self.timeline_id,
            "timeline_revision": self.timeline_revision,
            "timeline_fingerprint": self.timeline_fingerprint,
            "width": self.width,
            "height": self.height,
            "fps_numerator": self.fps_numerator,
            "fps_denominator": self.fps_denominator,
            "total_duration_ms": self.total_duration_ms,
            "required_backend": self.required_backend,
            "required_backend_revision": self.required_backend_revision,
            "items": [item.payload() for item in self.items],
            "captions": [item.payload() for item in self.captions],
        }

    def compute_fingerprint(self) -> str:
        canonical = json.dumps(
            self.payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ConditioningEvidence:
    """Measured evidence that the frozen source reached one backend execution."""

    source_sha256: str
    derivative_sha256: str
    derivative_width: int
    derivative_height: int
    reference_source_sha256: str | None = None
    reference_derivative_sha256: str | None = None
    control_fingerprint: str | None = None

    def __post_init__(self) -> None:
        for value, field in (
            (self.source_sha256, "conditioning source checksum"),
            (self.derivative_sha256, "conditioning derivative checksum"),
        ):
            if len(value) != SHA256_HEX_LENGTH or any(
                character not in "0123456789abcdef" for character in value
            ):
                raise DomainValidationError(f"{field} must be lowercase SHA-256")
        if self.derivative_width < 1 or self.derivative_height < 1:
            raise DomainValidationError("conditioning derivative dimensions must be positive")
        reference_values = (
            self.reference_source_sha256,
            self.reference_derivative_sha256,
            self.control_fingerprint,
        )
        if any(value is not None for value in reference_values):
            if any(value is None for value in reference_values):
                raise DomainValidationError("reference conditioning evidence must be complete")
            for reference_value in reference_values:
                assert reference_value is not None
                if len(reference_value) != SHA256_HEX_LENGTH or any(
                    character not in "0123456789abcdef" for character in reference_value
                ):
                    raise DomainValidationError(
                        "reference conditioning evidence must use lowercase SHA-256"
                    )


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    """Normalized request persisted before a job is queued."""

    prompt: str
    model: str
    resolution: Resolution
    frame_count: int
    seed: int
    mode: GenerationMode = GenerationMode.TEXT_TO_VIDEO
    image_conditioning: ImageConditioning | None = None
    rough_cut: RoughCutManifest | None = None
    timeline_render: TimelineRenderManifest | None = None

    def __post_init__(self) -> None:
        if self.prompt != self.prompt.strip():
            raise DomainValidationError("prompt must already be trimmed")
        if not 1 <= len(self.prompt) <= 2_000:
            raise DomainValidationError("prompt length must be between 1 and 2000")
        _require_non_empty(self.model, "model")
        if self.frame_count <= 0:
            raise DomainValidationError("frame_count must be positive")
        if not MIN_SEED <= self.seed <= MAX_SEED:
            raise DomainValidationError("seed must be a signed 64-bit integer")
        if self.mode is GenerationMode.TEXT_TO_VIDEO:
            if any(
                item is not None
                for item in (self.image_conditioning, self.rough_cut, self.timeline_render)
            ):
                raise DomainValidationError("text-to-video requests cannot contain manifests")
        elif self.mode is GenerationMode.IMAGE_TO_VIDEO:
            if (
                self.image_conditioning is None
                or self.rough_cut is not None
                or self.timeline_render is not None
            ):
                raise DomainValidationError(
                    "image-to-video requests require only image conditioning"
                )
        elif self.mode is GenerationMode.ROUGH_CUT:
            if (
                self.image_conditioning is not None
                or self.rough_cut is None
                or self.timeline_render is not None
            ):
                raise DomainValidationError("rough-cut requests require only a rough-cut manifest")
        elif (
            self.image_conditioning is not None
            or self.rough_cut is not None
            or self.timeline_render is None
        ):
            raise DomainValidationError(
                "timeline-render requests require only a timeline-render manifest"
            )
        if self.rough_cut is not None:
            if self.model != self.rough_cut.required_backend:
                raise DomainValidationError("rough-cut model must match the required backend")
            if self.resolution != Resolution(self.rough_cut.width, self.rough_cut.height):
                raise DomainValidationError("rough-cut resolution must match its manifest")
            if self.frame_count != self.rough_cut.frame_count:
                raise DomainValidationError("rough-cut frame count must match its manifest")
        if self.timeline_render is not None:
            if self.model != self.timeline_render.required_backend:
                raise DomainValidationError("timeline-render model must match its backend")
            if self.resolution != Resolution(
                self.timeline_render.width, self.timeline_render.height
            ):
                raise DomainValidationError("timeline-render resolution must match its manifest")
            if self.frame_count != self.timeline_render.frame_count:
                raise DomainValidationError("timeline-render frame count must match its manifest")

    @property
    def width(self) -> int:
        return self.resolution.width

    @property
    def height(self) -> int:
        return self.resolution.height


def normalize_request(
    draft: GenerationRequestDraft,
    capability: ModelCapability,
    generate_seed: Callable[[], int],
) -> GenerationRequest:
    """Normalize and validate a request against one enabled model capability."""

    prompt = draft.prompt.strip()
    if not 1 <= len(prompt) <= 2_000:
        raise DomainValidationError("prompt length must be between 1 and 2000")
    if not capability.enabled or draft.model != capability.model_id:
        raise DomainValidationError("model is unsupported or disabled")
    if draft.mode not in capability.modes:
        raise DomainValidationError("generation mode is unsupported")
    resolution = Resolution(draft.width, draft.height)
    if resolution not in capability.resolutions:
        raise DomainValidationError("resolution pair is unsupported")
    if draft.frame_count not in capability.frame_counts:
        raise DomainValidationError("frame_count is unsupported")
    seed = generate_seed() if draft.seed is None else draft.seed
    if not MIN_SEED <= seed <= MAX_SEED:
        raise DomainValidationError("seed must be a signed 64-bit integer")
    return GenerationRequest(
        prompt=prompt,
        model=draft.model,
        resolution=resolution,
        frame_count=draft.frame_count,
        seed=seed,
        mode=draft.mode,
    )


@dataclass(frozen=True, slots=True)
class Progress:
    """Truthful backend-confirmed progress."""

    completed_units: int
    total_units: int
    stage: str

    def __post_init__(self) -> None:
        if self.total_units <= 0:
            raise DomainValidationError("total_units must be positive")
        if not 0 <= self.completed_units <= self.total_units:
            raise DomainValidationError("completed_units must be within total_units")
        _require_non_empty(self.stage, "stage")


@dataclass(frozen=True, slots=True)
class GenerationResult:
    """Successful output metadata plus an internal opaque storage key."""

    storage_key: str
    media_type: str
    resolution: Resolution
    frame_count: int
    duration_seconds: float | None
    size_bytes: int
    sha256: str
    created_at: datetime

    def __post_init__(self) -> None:
        _require_non_empty(self.storage_key, "storage_key")
        if self.media_type != "video/mp4":
            raise DomainValidationError("MVP results must use video/mp4")
        if self.frame_count <= 0:
            raise DomainValidationError("frame_count must be positive")
        if self.duration_seconds is not None and self.duration_seconds <= 0:
            raise DomainValidationError("duration_seconds must be positive when present")
        if self.size_bytes <= 0:
            raise DomainValidationError("size_bytes must be positive")
        if len(self.sha256) != SHA256_HEX_LENGTH or any(
            character not in "0123456789abcdef" for character in self.sha256
        ):
            raise DomainValidationError("sha256 must be 64 lowercase hexadecimal characters")
        _require_utc_aware(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class Failure:
    """Safe failure details suitable for the public contract."""

    code: ErrorCode
    message: str
    retryable: bool
    job_id: str
    correlation_id: str

    def __post_init__(self) -> None:
        _require_non_empty(self.message, "message")
        _require_non_empty(self.job_id, "job_id")
        _require_non_empty(self.correlation_id, "correlation_id")


@dataclass(frozen=True, slots=True)
class BackendOutput:
    """A backend-produced temporary artifact awaiting safe storage."""

    temporary_path: Path
    resolution: Resolution
    frame_count: int
    duration_seconds: float | None
    conditioning_evidence: ConditioningEvidence | None = None

    def __post_init__(self) -> None:
        if not self.temporary_path.is_absolute():
            raise DomainValidationError("temporary_path must be absolute")
        if self.frame_count <= 0:
            raise DomainValidationError("frame_count must be positive")
        if self.duration_seconds is not None and self.duration_seconds <= 0:
            raise DomainValidationError("duration_seconds must be positive when present")
