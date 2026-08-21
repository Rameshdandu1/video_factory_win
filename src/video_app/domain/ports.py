"""Canonical framework-independent generation backend port."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from video_app.domain.models import (
    BackendOutput,
    ErrorCode,
    GenerationRequest,
    ModelCapability,
    Progress,
)

ProgressReporter = Callable[[Progress], Awaitable[None]]
CancellationProbe = Callable[[], Awaitable[bool]]


class BackendCancelledError(Exception):
    """Raised when a backend cooperatively stops after an application cancellation."""


class BackendFailureError(Exception):
    """Carry a stable backend failure classification without exposing raw details."""

    _ALLOWED_CODES = frozenset(
        {
            ErrorCode.UNSUPPORTED_PARAMETERS,
            ErrorCode.MODEL_UNAVAILABLE,
            ErrorCode.INSUFFICIENT_RESOURCES,
            ErrorCode.GENERATION_FAILED,
        }
    )

    def __init__(self, code: ErrorCode, *, retryable: bool) -> None:
        if code not in self._ALLOWED_CODES:
            raise ValueError("error code is not owned by generation backends")
        super().__init__(code.value)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class GenerationContext:
    """Worker-owned callbacks supplied to a generation backend."""

    job_id: str
    report_progress: ProgressReporter
    is_cancellation_requested: CancellationProbe

    def __post_init__(self) -> None:
        if not self.job_id or self.job_id.isspace():
            raise ValueError("job_id must not be empty")


@runtime_checkable
class GenerationBackend(Protocol):
    """The only interface application code uses to invoke a video backend."""

    @property
    def name(self) -> str:
        """Return a stable backend identifier."""
        ...

    @property
    def revision(self) -> str:
        """Return the exact code/model revision used for provenance."""
        ...

    def capabilities(self) -> tuple[ModelCapability, ...]:
        """Return backend-neutral enabled model capabilities."""
        ...

    async def generate(
        self,
        request: GenerationRequest,
        context: GenerationContext,
    ) -> BackendOutput:
        """Generate one temporary video while honoring progress and cancellation."""
        ...


@runtime_checkable
class CapabilityProvider(Protocol):
    """Expose model capabilities without constructing a model runtime."""

    def capabilities(self) -> tuple[ModelCapability, ...]: ...
