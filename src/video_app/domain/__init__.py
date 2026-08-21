"""Framework-independent domain contracts and rules."""

from video_app.domain.jobs import GenerationJob, InvalidTransitionError, JobStatus
from video_app.domain.models import (
    BackendOutput,
    DomainValidationError,
    ErrorCode,
    Failure,
    GenerationMode,
    GenerationRequest,
    GenerationRequestDraft,
    GenerationResult,
    ModelCapability,
    Progress,
    Resolution,
    normalize_request,
)
from video_app.domain.ports import GenerationBackend, GenerationContext

__all__ = [
    "BackendOutput",
    "DomainValidationError",
    "ErrorCode",
    "Failure",
    "GenerationBackend",
    "GenerationContext",
    "GenerationJob",
    "GenerationMode",
    "GenerationRequest",
    "GenerationRequestDraft",
    "GenerationResult",
    "InvalidTransitionError",
    "JobStatus",
    "ModelCapability",
    "Progress",
    "Resolution",
    "normalize_request",
]

