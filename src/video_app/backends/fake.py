"""Deterministic offline generation backend for development and tests."""

from __future__ import annotations

import asyncio
import os
import stat
import struct
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from video_app.domain.models import (
    BackendOutput,
    GenerationRequest,
    ModelCapability,
    Progress,
)
from video_app.domain.ports import BackendCancelledError, GenerationContext


class FakeBackendError(RuntimeError):
    """Raised for an explicitly configured fake-backend failure."""


def _is_reparse_point(path: Path) -> bool:
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _box(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", len(payload) + 8, kind) + payload


def _placeholder_mp4(request: GenerationRequest) -> bytes:
    """Create a deterministic MP4 container placeholder without private prompt text."""

    file_type = _box(b"ftyp", b"isom\x00\x00\x02\x00isomiso2mp41")
    metadata = (
        f"fake-backend;{request.width}x{request.height};"
        f"frames={request.frame_count};seed={request.seed}"
    ).encode("ascii")
    return file_type + _box(b"free", metadata)


def _write_atomic(partial_path: Path, final_path: Path, payload: bytes) -> None:
    with partial_path.open("xb") as output:
        output.write(payload)
        output.flush()
        os.fsync(output.fileno())
    os.replace(partial_path, final_path)


def _remove_if_present(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return


@dataclass(frozen=True, slots=True)
class FakeBackend:
    """A bounded fake that behaves like a cooperative generation backend."""

    output_root: Path
    model_capabilities: tuple[ModelCapability, ...]
    steps: int = 3
    step_delay_seconds: float = 0.0
    fail_after_step: int | None = None

    def __post_init__(self) -> None:
        root = self.output_root
        if not root.is_absolute():
            raise ValueError("fake output_root must be absolute")
        if not root.exists() or not root.is_dir():
            raise ValueError("fake output_root must be an existing directory")
        if root.is_symlink() or _is_reparse_point(root):
            raise ValueError("fake output_root must not be a link or reparse point")
        if not self.model_capabilities:
            raise ValueError("fake backend requires at least one model capability")
        if self.steps <= 0:
            raise ValueError("steps must be positive")
        if self.step_delay_seconds < 0:
            raise ValueError("step_delay_seconds cannot be negative")
        if self.fail_after_step is not None and not 1 <= self.fail_after_step <= self.steps:
            raise ValueError("fail_after_step must identify a configured step")

    @property
    def name(self) -> str:
        return "fake"

    @property
    def revision(self) -> str:
        return "fake-v1"

    def capabilities(self) -> tuple[ModelCapability, ...]:
        return self.model_capabilities

    def _supports(self, request: GenerationRequest) -> bool:
        return any(
            capability.enabled
            and request.model == capability.model_id
            and request.mode in capability.modes
            and request.resolution in capability.resolutions
            and request.frame_count in capability.frame_counts
            for capability in self.model_capabilities
        )

    async def generate(
        self,
        request: GenerationRequest,
        context: GenerationContext,
    ) -> BackendOutput:
        if not self._supports(request):
            raise FakeBackendError("request is outside fake backend capabilities")

        root = self.output_root.resolve(strict=True)
        opaque_name = uuid4().hex
        partial_path = root / f"{opaque_name}.part"
        final_path = root / f"{opaque_name}.mp4"
        if partial_path.parent != root or final_path.parent != root:
            raise FakeBackendError("generated path escaped fake output_root")

        try:
            for step in range(1, self.steps + 1):
                if await context.is_cancellation_requested():
                    raise BackendCancelledError
                if self.step_delay_seconds:
                    await asyncio.sleep(self.step_delay_seconds)
                await context.report_progress(
                    Progress(
                        completed_units=step,
                        total_units=self.steps,
                        stage="fake_generation",
                    )
                )
                if self.fail_after_step == step:
                    raise FakeBackendError(f"configured failure after step {step}")

            if await context.is_cancellation_requested():
                raise BackendCancelledError
            payload = _placeholder_mp4(request)
            await asyncio.to_thread(_write_atomic, partial_path, final_path, payload)
            return BackendOutput(
                temporary_path=final_path,
                resolution=request.resolution,
                frame_count=request.frame_count,
                duration_seconds=None,
            )
        except BaseException:
            await asyncio.to_thread(_remove_if_present, partial_path)
            await asyncio.to_thread(_remove_if_present, final_path)
            raise
