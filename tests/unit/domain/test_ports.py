from __future__ import annotations

import unittest
from pathlib import Path

from video_app.domain.models import (
    BackendOutput,
    ErrorCode,
    GenerationRequest,
    ModelCapability,
    Resolution,
)
from video_app.domain.ports import BackendFailureError, GenerationBackend, GenerationContext


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

    def test_backend_failure_accepts_every_backend_owned_error_code(self) -> None:
        for code in (
            ErrorCode.UNSUPPORTED_PARAMETERS,
            ErrorCode.MODEL_UNAVAILABLE,
            ErrorCode.INSUFFICIENT_RESOURCES,
            ErrorCode.GENERATION_FAILED,
        ):
            with self.subTest(code=code):
                error = BackendFailureError(code, retryable=True)

                self.assertEqual(error.code, code)
                self.assertTrue(error.retryable)
                self.assertEqual(str(error), code.value)

    def test_backend_failure_rejects_error_codes_owned_by_other_layers(self) -> None:
        with self.assertRaisesRegex(ValueError, "not owned"):
            BackendFailureError(ErrorCode.OUTPUT_WRITE_FAILED, retryable=False)


if __name__ == "__main__":
    unittest.main()
