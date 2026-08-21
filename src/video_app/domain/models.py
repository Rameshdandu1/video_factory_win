"""Immutable value objects implementing Generation Contract v1."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
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
class GenerationRequest:
    """Normalized request persisted before a job is queued."""

    prompt: str
    model: str
    resolution: Resolution
    frame_count: int
    seed: int
    mode: GenerationMode = GenerationMode.TEXT_TO_VIDEO

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

    def __post_init__(self) -> None:
        if not self.temporary_path.is_absolute():
            raise DomainValidationError("temporary_path must be absolute")
        if self.frame_count <= 0:
            raise DomainValidationError("frame_count must be positive")
        if self.duration_seconds is not None and self.duration_seconds <= 0:
            raise DomainValidationError("duration_seconds must be positive when present")
