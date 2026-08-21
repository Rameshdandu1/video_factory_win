from __future__ import annotations

import unittest
from pathlib import Path

from video_app.domain.models import BackendOutput, GenerationRequest, ModelCapability, Resolution
from video_app.domain.ports import GenerationBackend, GenerationContext


class FakeBackend:
    name = "fake"
    revision = "fake-v1"

    def capabilities(self) -> tuple[ModelCapability, ...]:
        return ()

    async def generate(
        self,
        request: GenerationRequest,
        context: GenerationContext,
    ) -> BackendOutput:
        raise NotImplementedError


class BackendProtocolTests(unittest.TestCase):
    def test_structural_backend_implements_canonical_protocol(self) -> None:
        self.assertIsInstance(FakeBackend(), GenerationBackend)

    def test_backend_output_rejects_relative_temporary_path(self) -> None:
        with self.assertRaises(ValueError):
            BackendOutput(
                Path("relative.mp4"),
                resolution=Resolution(832, 480),
                frame_count=1,
                duration_seconds=1,
            )


if __name__ == "__main__":
    unittest.main()
