"""Qualified Wan2.2-Animate animation/replacement adapter."""

from video_app.backends.controlled import ControlledRuntime, ControlledVideoBackend
from video_app.domain.models import ControlledVideoOperation

ANIMATE_CODE_REVISION = "29d4a35d32273d5309a3a95250bd4e118d8789b2"
ANIMATE_MODEL_REVISION = "cb93a225fbaf1ca100f54e79da8f994995b689b3"
ANIMATE_MODEL_ID = "wan22-animate-14b"
ANIMATE_TASK = "animate-14B"
ANIMATE_BACKEND_REVISION = (
    f"wan2.2@{ANIMATE_CODE_REVISION};task={ANIMATE_TASK};"
    f"model=Wan-AI/Wan2.2-Animate-14B@{ANIMATE_MODEL_REVISION}"
)


class WanAnimateBackend(ControlledVideoBackend):
    """Constrain the shared process boundary to one explicit Animate operation."""

    def __init__(self, runtime: ControlledRuntime) -> None:
        if not runtime.operations or not runtime.operations <= {
            ControlledVideoOperation.ANIMATE_CHARACTER,
            ControlledVideoOperation.ANIMATE_REPLACEMENT,
        }:
            raise ValueError("Wan Animate requires animation or replacement")
        super().__init__(runtime)
