"""Revision-pinned Wan2.2 TI2V backend adapter."""

from video_app.backends.wan22.adapter import (
    WAN22_BACKEND_REVISION,
    WAN22_CODE_REVISION,
    WAN22_MODEL_ID,
    WAN22_MODEL_REVISION,
    Wan22Backend,
    Wan22ConfigurationError,
)

__all__ = [
    "WAN22_BACKEND_REVISION",
    "WAN22_CODE_REVISION",
    "WAN22_MODEL_ID",
    "WAN22_MODEL_REVISION",
    "Wan22Backend",
    "Wan22ConfigurationError",
]
