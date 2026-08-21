from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import pytest

from video_app.backends.wan21.adapter import WAN21_MODEL_REVISIONS, Wan21Backend
from video_app.domain.models import (
    GenerationMode,
    GenerationRequest,
    ModelCapability,
    Progress,
    Resolution,
)
from video_app.domain.ports import GenerationContext

pytestmark = [pytest.mark.gpu, pytest.mark.integration]

_RUN_GPU = os.environ.get("VIDEO_APP_RUN_WAN21_GPU_TESTS") == "1"
_REPOSITORY_ROOT = os.environ.get("VIDEO_APP_WAN21_REPOSITORY_ROOT")
_CHECKPOINT_DIR = os.environ.get("VIDEO_APP_WAN21_CHECKPOINT_DIR")
_PYTHON_EXECUTABLE = os.environ.get("VIDEO_APP_WAN21_PYTHON")
_TASK = os.environ.get("VIDEO_APP_WAN21_TASK", "t2v-1.3B")
_CONFIGURED = all((_REPOSITORY_ROOT, _CHECKPOINT_DIR, _PYTHON_EXECUTABLE))


@unittest.skipUnless(
    _RUN_GPU and _CONFIGURED,
    "set VIDEO_APP_RUN_WAN21_GPU_TESTS=1 and Wan2.1 runtime paths",
)
class Wan21GpuSmokeTests(unittest.IsolatedAsyncioTestCase):
    async def test_pinned_runtime_generates_one_local_mp4_without_network(self) -> None:
        assert _REPOSITORY_ROOT is not None
        assert _CHECKPOINT_DIR is not None
        assert _PYTHON_EXECUTABLE is not None
        resolution = Resolution(832, 480)
        capability = ModelCapability(
            model_id="wan21-t2v",
            display_name="Wan2.1 Text to Video",
            modes=frozenset({GenerationMode.TEXT_TO_VIDEO}),
            resolutions=frozenset({resolution}),
            frame_counts=frozenset({81}),
        )
        request = GenerationRequest(
            prompt="A red paper boat drifting across a still pond",
            model="wan21-t2v",
            resolution=resolution,
            frame_count=81,
            seed=42,
        )
        reported: list[Progress] = []

        async def report(progress: Progress) -> None:
            reported.append(progress)

        async def not_cancelled() -> bool:
            return False

        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory).resolve()
            backend = Wan21Backend(
                repository_root=Path(_REPOSITORY_ROOT).resolve(strict=True),
                checkpoint_dir=Path(_CHECKPOINT_DIR).resolve(strict=True),
                python_executable=Path(_PYTHON_EXECUTABLE).resolve(strict=True),
                output_root=output_root,
                task=_TASK,
                model_revision=WAN21_MODEL_REVISIONS[_TASK],
                model_capabilities=(capability,),
                cancellation_poll_seconds=1.0,
                termination_grace_seconds=10.0,
            )

            output = await backend.generate(
                request,
                GenerationContext("gpu-smoke-job", report, not_cancelled),
            )

            self.assertTrue(output.temporary_path.is_file())
            self.assertGreater(output.temporary_path.stat().st_size, 12)
            with output.temporary_path.open("rb") as video:
                self.assertEqual(video.read(8)[4:8], b"ftyp")
            self.assertEqual(output.resolution, resolution)
            self.assertEqual(output.frame_count, 81)
            self.assertEqual(reported, [])


if __name__ == "__main__":
    unittest.main()
