"""Pinned Wan2.1 generation backend adapter."""

from video_app.backends.wan21.adapter import (
    WAN21_CODE_REVISION,
    WAN21_MODEL_REVISIONS,
    Wan21Backend,
    Wan21ConfigurationError,
)

__all__ = [
    "WAN21_CODE_REVISION",
    "WAN21_MODEL_REVISIONS",
    "Wan21Backend",
    "Wan21ConfigurationError",
]
