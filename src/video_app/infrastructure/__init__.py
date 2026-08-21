"""Concrete persistence, queue, storage, and telemetry adapters."""

from video_app.infrastructure.storage import LocalArtifactStore

__all__ = ["LocalArtifactStore"]
