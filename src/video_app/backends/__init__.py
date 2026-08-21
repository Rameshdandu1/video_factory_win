"""Video-generation backend adapters."""

from video_app.backends.fake import FakeBackend, FakeBackendError

__all__ = ["FakeBackend", "FakeBackendError"]

