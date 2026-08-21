from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from video_app.backends.fake import FakeBackend, FakeBackendError
from video_app.domain.models import (
    GenerationMode,
    GenerationRequest,
    ModelCapability,
    Progress,
    Resolution,
)
from video_app.domain.ports import BackendCancelledError, GenerationBackend, GenerationContext

RESOLUTION = Resolution(832, 480)
CAPABILITY = ModelCapability(
    model_id="wan21-t2v",
    display_name="Wan2.1 Text to Video",
    modes=frozenset({GenerationMode.TEXT_TO_VIDEO}),
    resolutions=frozenset({RESOLUTION}),
    frame_counts=frozenset({81}),
)
REQUEST = GenerationRequest("private prompt", "wan21-t2v", RESOLUTION, 81, 42)


class FakeBackendTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.output_root = Path(self.temporary_directory.name).resolve()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def backend(
        self,
        *,
        steps: int = 3,
        step_delay_seconds: float = 0.0,
        fail_after_step: int | None = None,
    ) -> FakeBackend:
        return FakeBackend(
            output_root=self.output_root,
            model_capabilities=(CAPABILITY,),
            steps=steps,
            step_delay_seconds=step_delay_seconds,
            fail_after_step=fail_after_step,
        )

    async def test_generates_atomic_placeholder_and_reports_truthful_progress(self) -> None:
        progress: list[Progress] = []

        async def report(value: Progress) -> None:
            progress.append(value)

        async def not_cancelled() -> bool:
            return False

        backend = self.backend(steps=3)
        output = await backend.generate(
            REQUEST,
            GenerationContext("job-1", report, not_cancelled),
        )

        self.assertIsInstance(backend, GenerationBackend)
        self.assertEqual([item.completed_units for item in progress], [1, 2, 3])
        self.assertEqual(output.resolution, REQUEST.resolution)
        self.assertEqual(output.frame_count, REQUEST.frame_count)
        self.assertTrue(output.temporary_path.is_file())
        self.assertEqual(output.temporary_path.parent, self.output_root)
        payload = output.temporary_path.read_bytes()
        self.assertIn(b"ftyp", payload)
        self.assertNotIn(REQUEST.prompt.encode(), payload)
        self.assertEqual(list(self.output_root.glob("*.part")), [])

    async def test_cancellation_is_cooperative_and_cleans_files(self) -> None:
        checks = 0

        async def report(_: Progress) -> None:
            return None

        async def cancel_during_generation() -> bool:
            nonlocal checks
            checks += 1
            return checks >= 2

        with self.assertRaises(BackendCancelledError):
            await self.backend(steps=3).generate(
                REQUEST,
                GenerationContext("job-1", report, cancel_during_generation),
            )

        self.assertEqual(list(self.output_root.iterdir()), [])

    async def test_configured_failure_cleans_files(self) -> None:
        async def report(_: Progress) -> None:
            return None

        async def not_cancelled() -> bool:
            return False

        with self.assertRaisesRegex(FakeBackendError, "configured failure"):
            await self.backend(fail_after_step=2).generate(
                REQUEST,
                GenerationContext("job-1", report, not_cancelled),
            )

        self.assertEqual(list(self.output_root.iterdir()), [])

    async def test_rejects_request_outside_capabilities_without_writing(self) -> None:
        unsupported = GenerationRequest("prompt", "other-model", RESOLUTION, 81, 42)

        async def report(_: Progress) -> None:
            return None

        async def not_cancelled() -> bool:
            return False

        with self.assertRaisesRegex(FakeBackendError, "outside"):
            await self.backend().generate(
                unsupported,
                GenerationContext("job-1", report, not_cancelled),
            )

        self.assertEqual(list(self.output_root.iterdir()), [])

    def test_configuration_requires_safe_existing_absolute_root(self) -> None:
        with self.assertRaisesRegex(ValueError, "absolute"):
            FakeBackend(Path("relative"), (CAPABILITY,))


if __name__ == "__main__":
    unittest.main()
