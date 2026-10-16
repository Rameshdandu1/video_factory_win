from __future__ import annotations

import asyncio
import os
import signal
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

from video_app.backends.controlled import (
    ControlledRuntime,
    ControlledVideoBackend,
)
from video_app.domain.models import (
    ControlledVideoOperation,
    GenerationMode,
    GenerationRequest,
    ImageConditioning,
    ReferenceVideoConditioning,
    Resolution,
)
from video_app.domain.ports import BackendCancelledError, GenerationContext


def runtime(*operations: ControlledVideoOperation) -> ControlledRuntime:
    return cast(
        ControlledRuntime,
        SimpleNamespace(
            backend_name="controlled",
            backend_revision="controlled@revision",
            model_id="controlled-model",
            display_name="Controlled test model",
            task="controlled-task",
            operations=frozenset(operations),
            repository_root=Path("C:/runtime/repository"),
            checkpoint_dir=Path("C:/runtime/checkpoint"),
            python_executable=Path("C:/runtime/python.exe"),
            ffmpeg_executable=Path("C:/runtime/ffmpeg.exe"),
            output_root=Path("C:/runtime/output"),
            resolution=Resolution(832, 480),
            frame_count=81,
            input_fps=16,
            minimum_free_disk_bytes=1,
            minimum_free_vram_bytes=1,
            deadline_seconds=60,
            cancellation_poll_seconds=0.001,
            termination_grace_seconds=0.01,
        ),
    )


def request(operation: ControlledVideoOperation) -> GenerationRequest:
    reference = ReferenceVideoConditioning(
        guidance_id="guidance",
        guidance_revision=1,
        guidance_fingerprint="a" * 64,
        purpose="motion_performance",
        source_asset_id="video",
        source_asset_version=1,
        source_asset_sha256="b" * 64,
        source_storage_key="uploads/video.mp4",
        trim_start_ms=1_000,
        trim_end_ms=4_000,
        operation=operation,
        preserve_environment=operation is ControlledVideoOperation.VACE_PERFORMANCE_TRANSFER,
        constraint_plan_fingerprint="c" * 64,
    )
    conditioning = ImageConditioning(
        owner_id="owner",
        project_id="project",
        shot_id="shot",
        shot_version=1,
        composition_id="composition",
        composition_revision=1,
        composition_fingerprint="d" * 64,
        source_asset_id="image",
        source_asset_version=1,
        source_asset_sha256="e" * 64,
        source_storage_key="uploads/image.png",
        source_width=832,
        source_height=480,
        required_backend="controlled",
        required_backend_revision="controlled@revision",
        manifest_fingerprint="f" * 64,
        reference_video=reference,
    )
    return GenerationRequest(
        prompt="private prompt",
        model="controlled-model",
        resolution=Resolution(832, 480),
        frame_count=81,
        seed=-1,
        mode=GenerationMode.IMAGE_TO_VIDEO,
        image_conditioning=conditioning,
    )


class HangingProcess:
    def __init__(self) -> None:
        self.returncode: int | None = None
        self.pid = 7
        self.terminated = False

    async def communicate(self, _: bytes | None = None) -> tuple[bytes, bytes]:
        await asyncio.Event().wait()
        return b"", b""

    async def wait(self) -> int:
        return 0 if self.returncode is None else self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -1

    def kill(self) -> None:
        self.returncode = -9


class ControlledBackendTests(unittest.IsolatedAsyncioTestCase):
    def test_vace_command_assigns_approved_frame_and_reference_to_distinct_roles(self) -> None:
        backend = ControlledVideoBackend(
            runtime(ControlledVideoOperation.VACE_PERFORMANCE_TRANSFER)
        )
        image = Path("C:/work/approved-frame.png")
        video = Path("C:/work/trimmed-reference.mp4")
        generated = backend._vace_command(
            request(ControlledVideoOperation.VACE_PERFORMANCE_TRANSFER),
            image,
            video,
            Path("C:/work/controls"),
            Path("C:/work/output.mp4"),
        )

        self.assertEqual(generated[generated.index("--image") + 1], str(image))
        self.assertEqual(generated[generated.index("--video") + 1], str(video))
        self.assertEqual(generated[generated.index("--task") + 1], "animate_anything")
        self.assertEqual(generated[generated.index("--mode") + 1], "salientbboxtrack")

    def test_animate_preprocess_keeps_character_and_replacement_modes_explicit(self) -> None:
        backend = ControlledVideoBackend(
            runtime(
                ControlledVideoOperation.ANIMATE_CHARACTER,
                ControlledVideoOperation.ANIMATE_REPLACEMENT,
            )
        )
        paths = (
            Path("C:/work/approved-frame.png"),
            Path("C:/work/trimmed-reference.mp4"),
            Path("C:/work/controls"),
        )

        animation = backend._animate_preprocess_command(
            ControlledVideoOperation.ANIMATE_CHARACTER, *paths
        )
        replacement = backend._animate_preprocess_command(
            ControlledVideoOperation.ANIMATE_REPLACEMENT, *paths
        )

        self.assertIn("--retarget_flag", animation)
        self.assertNotIn("--replace_flag", animation)
        self.assertIn("--replace_flag", replacement)
        self.assertNotIn("--retarget_flag", replacement)
        self.assertEqual(animation[animation.index("--video_path") + 1], str(paths[1]))
        self.assertEqual(animation[animation.index("--refer_path") + 1], str(paths[0]))

    def test_backend_rejects_an_operation_outside_its_qualified_set(self) -> None:
        backend = ControlledVideoBackend(
            runtime(ControlledVideoOperation.VACE_PERFORMANCE_TRANSFER)
        )
        self.assertFalse(backend._supports(request(ControlledVideoOperation.ANIMATE_CHARACTER)))

    async def test_cancellation_stops_the_isolated_process_tree(self) -> None:
        process = HangingProcess()

        async def spawn(*_: object, **__: object) -> HangingProcess:
            return process

        async def report(_: object) -> None:
            return None

        async def cancelled() -> bool:
            return True

        backend = ControlledVideoBackend(
            runtime(ControlledVideoOperation.VACE_PERFORMANCE_TRANSFER)
        )
        context = GenerationContext("job", report, cancelled)
        with (
            patch(
                "video_app.backends.controlled.asyncio.create_subprocess_exec",
                new=spawn,
            ),
            patch("video_app.backends.controlled.os.killpg", create=True) as kill_group,
            self.assertRaises(BackendCancelledError),
        ):
            await backend._run(("worker",), context)

        if os.name == "nt":
            self.assertTrue(process.terminated)
        else:
            kill_group.assert_called_once_with(process.pid, signal.SIGTERM)


if __name__ == "__main__":
    unittest.main()
