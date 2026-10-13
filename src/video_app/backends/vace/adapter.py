"""Qualified VACE Wan2.1 performance-transfer adapter."""

from video_app.backends.controlled import ControlledRuntime, ControlledVideoBackend
from video_app.domain.models import ControlledVideoOperation

VACE_CODE_REVISION = "48eb44f1c4be87cc65a98bff985a26976841e9f3"
VACE_MODEL_REVISION = "c76cda849bfb74d563b95f3db039421e9df2a570"
VACE_MODEL_ID = "vace-wan21-1.3b-performance"
VACE_TASK = "animate_anything:salientbboxtrack"
VACE_BACKEND_REVISION = (
    f"vace@{VACE_CODE_REVISION};task={VACE_TASK};"
    f"model=ali-vilab/VACE-Wan2.1-1.3B-Preview@{VACE_MODEL_REVISION}"
)


class VaceBackend(ControlledVideoBackend):
    """Constrain the shared process boundary to the reviewed VACE operation."""

    def __init__(self, runtime: ControlledRuntime) -> None:
        if runtime.operations != frozenset({ControlledVideoOperation.VACE_PERFORMANCE_TRANSFER}):
            raise ValueError("VACE requires the performance-transfer operation")
        super().__init__(runtime)
