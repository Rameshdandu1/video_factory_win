"""Canonical framework-independent generation backend port."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol, runtime_checkable

from video_app.domain.models import (
    BackendOutput,
    GenerationRequest,
    ModelCapability,
    Progress,
)

ProgressReporter = Callable[[Progress], Awaitable[None]]
CancellationProbe = Callable[[], Awaitable[bool]]


class BackendCancelledError(Exception):
    """Raised when a backend cooperatively stops after an application cancellation."""


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
