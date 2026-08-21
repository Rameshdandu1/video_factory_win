from __future__ import annotations

import asyncio
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Mapping
from pathlib import Path
from typing import cast
from unittest.mock import patch

from video_app.backends.wan21.adapter import (
    WAN21_CODE_REVISION,
    WAN21_MODEL_REVISIONS,
    Wan21Backend,
)
from video_app.domain.models import (
    MAX_SEED,
    MIN_SEED,
    ErrorCode,
    GenerationMode,
    GenerationRequest,
    ModelCapability,
    Progress,
    Resolution,
)
from video_app.domain.ports import (
    BackendCancelledError,
    BackendFailureError,
    CancellationProbe,
    GenerationContext,
)

RESOLUTION = Resolution(832, 480)
CAPABILITY = ModelCapability(
    model_id="wan21-t2v",
    display_name="Wan2.1 Text to Video",
    modes=frozenset({GenerationMode.TEXT_TO_VIDEO}),
    resolutions=frozenset({RESOLUTION}),
    frame_counts=frozenset({81}),
)
REQUEST = GenerationRequest(
    prompt='private prompt with shell characters: " & | ; $()',
    model="wan21-t2v",
    resolution=RESOLUTION,
    frame_count=81,
    seed=42,
)
TASK = "t2v-1.3B"


def _mp4_box(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", len(payload) + 8, kind) + payload


MP4_PAYLOAD = (
    _mp4_box(b"ftyp", b"isom\x00\x00\x02\x00isomiso2")
    + _mp4_box(b"moov", b"\x00")
    + _mp4_box(b"mdat", b"\x00")
)
TRUNCATED_MP4_PAYLOAD = MP4_PAYLOAD[:-1]


def _argument_value(arguments: tuple[str, ...], name: str) -> str:
    index = arguments.index(name)
    return arguments[index + 1]


class FakeProcess:
    def __init__(self, returncode: int | None, *, ignore_terminate: bool = False) -> None:
        self.returncode = returncode
        self.ignore_terminate = ignore_terminate
        self.terminated = False
        self.killed = False
        self.stdin_payload: bytes | None = None
        self.termination_requested = asyncio.Event()
        self._done = asyncio.Event()
        if returncode is not None:
            self._done.set()

    async def wait(self) -> int:
        await self._done.wait()
        assert self.returncode is not None
        return self.returncode

    async def communicate(
        self,
        input: bytes | None = None,
    ) -> tuple[bytes, bytes]:
        self.stdin_payload = input
        await self.wait()
        return b"", b""

    def terminate(self) -> None:
        self.terminated = True
        self.termination_requested.set()
        if not self.ignore_terminate:
            self.returncode = -15
            self._done.set()

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9
        self._done.set()


class Wan21BackendTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name).resolve()
        self.repository_root = root / "Wan2.1"
        self.checkpoint_dir = root / "checkpoint"
        self.output_root = root / "outputs"
        self.repository_root.mkdir()
        self.checkpoint_dir.mkdir()
        self.output_root.mkdir()
        (self.repository_root / "generate.py").write_text(
            "# upstream entry point placeholder\n",
            encoding="utf-8",
        )
        self.python_executable = Path(sys.executable).resolve()
        self.spawn_arguments: tuple[str, ...] | None = None
        self.spawn_options: dict[str, object] | None = None
        self.spawn_returncode: int | None = 0
        self.candidate_payload: bytes | None = MP4_PAYLOAD
        self.ignore_terminate = False
        self.spawn_error: OSError | None = None
        self.process: FakeProcess | None = None

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def backend(self, *, termination_grace_seconds: float = 0.01) -> Wan21Backend:
        return Wan21Backend(
            repository_root=self.repository_root,
            checkpoint_dir=self.checkpoint_dir,
            python_executable=self.python_executable,
            output_root=self.output_root,
            task=TASK,
            model_revision=WAN21_MODEL_REVISIONS[TASK],
            model_capabilities=(CAPABILITY,),
            cancellation_poll_seconds=0.001,
            termination_grace_seconds=termination_grace_seconds,
        )

    async def spawn(self, *arguments: object, **options: object) -> FakeProcess:
        normalized = tuple(str(item) for item in arguments)
        self.spawn_arguments = normalized
        self.spawn_options = options
        if self.spawn_error is not None:
            raise self.spawn_error
        if self.candidate_payload is not None:
            candidate = Path(_argument_value(normalized, "--save_file"))
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_bytes(self.candidate_payload)
        process = FakeProcess(self.spawn_returncode, ignore_terminate=self.ignore_terminate)
        self.process = process
        return process

    @staticmethod
    def context(
        cancellation_probe: CancellationProbe | None = None,
    ) -> tuple[GenerationContext, list[Progress]]:
        reported: list[Progress] = []

        async def report(progress: Progress) -> None:
            reported.append(progress)

        async def not_cancelled() -> bool:
            return False

        probe = not_cancelled if cancellation_probe is None else cancellation_probe
        return GenerationContext("job-1", report, probe), reported

    async def test_success_translates_command_and_does_not_expose_secrets_to_environment(
        self,
    ) -> None:
        context, reported = self.context()
        secret_environment = {
            "DATABASE_URL": "postgresql://user:private-password@localhost/database",
            "VIDEO_APP_CURSOR_SECRET": "private-cursor-secret",
        }
        with (
            patch.dict(os.environ, secret_environment, clear=False),
            patch(
                "video_app.backends.wan21.adapter._current_repository_revision",
                return_value=WAN21_CODE_REVISION,
            ),
            patch(
                "video_app.backends.wan21.adapter.asyncio.create_subprocess_exec",
                new=self.spawn,
            ),
        ):
            output = await self.backend().generate(REQUEST, context)

        assert self.spawn_arguments is not None
        assert self.spawn_options is not None
        arguments = self.spawn_arguments
        self.assertEqual(arguments[0], str(self.python_executable))
        self.assertEqual(arguments[1], "-c")
        wrapper = arguments[2]
        self.assertNotIn(REQUEST.prompt, wrapper)
        self.assertIn("imageio.get_reader(output_path)", wrapper)
        self.assertIn("decoded_frames", wrapper)
        self.assertIn("frame.shape[:2]", wrapper)
        self.assertEqual(_argument_value(arguments, "--task"), TASK)
        self.assertEqual(_argument_value(arguments, "--size"), "832*480")
        self.assertEqual(_argument_value(arguments, "--ckpt_dir"), str(self.checkpoint_dir))
        self.assertEqual(_argument_value(arguments, "--frame_num"), "81")
        self.assertEqual(_argument_value(arguments, "--base_seed"), "42")
        self.assertNotIn("--prompt", arguments)
        self.assertNotIn(REQUEST.prompt, arguments)
        save_file = Path(_argument_value(arguments, "--save_file"))
        self.assertTrue(save_file.is_absolute())
        self.assertTrue(save_file.is_relative_to(self.output_root))
        self.assertNotIn("shell", self.spawn_options)
        working_directory = self.spawn_options.get("cwd")
        self.assertIsNotNone(working_directory)
        self.assertEqual(Path(str(working_directory)), self.repository_root)
        self.assertEqual(self.spawn_options.get("stdin"), asyncio.subprocess.PIPE)
        self.assertEqual(self.spawn_options.get("stdout"), asyncio.subprocess.DEVNULL)
        self.assertEqual(self.spawn_options.get("stderr"), asyncio.subprocess.DEVNULL)
        if os.name == "nt":
            self.assertEqual(
                self.spawn_options.get("creationflags"),
                int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)),
            )
        else:
            self.assertIs(self.spawn_options.get("start_new_session"), True)
        environment_value = self.spawn_options.get("env")
        self.assertIsInstance(environment_value, Mapping)
        environment = cast(Mapping[str, str], environment_value)
        self.assertNotIn("DATABASE_URL", environment)
        self.assertNotIn("VIDEO_APP_CURSOR_SECRET", environment)
        self.assertNotIn(REQUEST.prompt, environment.values())
        self.assertEqual(environment.get("HF_HUB_OFFLINE"), "1")
        self.assertEqual(environment.get("TRANSFORMERS_OFFLINE"), "1")
        assert self.process is not None
        self.assertEqual(self.process.stdin_payload, REQUEST.prompt.encode("utf-8"))
        self.assertEqual(output.resolution, REQUEST.resolution)
        self.assertEqual(output.frame_count, REQUEST.frame_count)
        self.assertTrue(output.temporary_path.is_file())
        self.assertEqual(output.temporary_path.read_bytes(), MP4_PAYLOAD)
        self.assertEqual(reported, [])

    async def test_signed_seed_boundaries_map_to_equivalent_unsigned_cli_seed(self) -> None:
        cases = (
            (MIN_SEED, 2**63),
            (-1, 2**64 - 1),
            (0, 0),
            (MAX_SEED, MAX_SEED),
        )
        context, _ = self.context()
        with (
            patch(
                "video_app.backends.wan21.adapter._current_repository_revision",
                return_value=WAN21_CODE_REVISION,
            ),
            patch(
                "video_app.backends.wan21.adapter.asyncio.create_subprocess_exec",
                new=self.spawn,
            ),
        ):
            backend = self.backend()
            for seed, expected in cases:
                with self.subTest(seed=seed):
                    request = GenerationRequest(
                        prompt="private prompt",
                        model="wan21-t2v",
                        resolution=RESOLUTION,
                        frame_count=81,
                        seed=seed,
                    )
                    output = await backend.generate(request, context)
                    assert self.spawn_arguments is not None
                    self.assertEqual(
                        _argument_value(self.spawn_arguments, "--base_seed"),
                        str(expected),
                    )
                    output.temporary_path.unlink()

    async def test_nonzero_exit_is_safely_mapped_and_candidate_is_removed(self) -> None:
        self.spawn_returncode = 9
        context, _ = self.context()
        with (
            patch(
                "video_app.backends.wan21.adapter._current_repository_revision",
                return_value=WAN21_CODE_REVISION,
            ),
            patch(
                "video_app.backends.wan21.adapter.asyncio.create_subprocess_exec",
                new=self.spawn,
            ),
            self.assertRaises(BackendFailureError) as raised,
        ):
            await self.backend().generate(REQUEST, context)

        self.assertEqual(raised.exception.code, ErrorCode.GENERATION_FAILED)
        self.assertNotIn(REQUEST.prompt, str(raised.exception))
        self.assertNotIn(str(self.checkpoint_dir), str(raised.exception))
        self.assertEqual(list(self.output_root.rglob("*")), [])

    async def test_zero_exit_without_output_is_failure_and_cleans_temporary_files(self) -> None:
        self.candidate_payload = None
        context, _ = self.context()
        with (
            patch(
                "video_app.backends.wan21.adapter._current_repository_revision",
                return_value=WAN21_CODE_REVISION,
            ),
            patch(
                "video_app.backends.wan21.adapter.asyncio.create_subprocess_exec",
                new=self.spawn,
            ),
            self.assertRaises(BackendFailureError) as raised,
        ):
            await self.backend().generate(REQUEST, context)

        self.assertEqual(raised.exception.code, ErrorCode.GENERATION_FAILED)
        self.assertEqual(list(self.output_root.rglob("*")), [])

    async def test_zero_exit_with_truncated_mp4_is_failure_and_removes_candidate(self) -> None:
        self.candidate_payload = TRUNCATED_MP4_PAYLOAD
        context, _ = self.context()
        with (
            patch(
                "video_app.backends.wan21.adapter._current_repository_revision",
                return_value=WAN21_CODE_REVISION,
            ),
            patch(
                "video_app.backends.wan21.adapter.asyncio.create_subprocess_exec",
                new=self.spawn,
            ),
            self.assertRaises(BackendFailureError) as raised,
        ):
            await self.backend().generate(REQUEST, context)

        self.assertEqual(raised.exception.code, ErrorCode.GENERATION_FAILED)
        self.assertEqual(list(self.output_root.rglob("*")), [])

    async def test_cancellation_before_spawn_does_not_create_a_process_or_output(self) -> None:
        async def cancellation_requested() -> bool:
            return True

        context, _ = self.context(cancellation_requested)
        with (
            patch(
                "video_app.backends.wan21.adapter._current_repository_revision",
                return_value=WAN21_CODE_REVISION,
            ),
            patch(
                "video_app.backends.wan21.adapter.asyncio.create_subprocess_exec",
                new=self.spawn,
            ),
            self.assertRaises(BackendCancelledError),
        ):
            await self.backend().generate(REQUEST, context)

        self.assertIsNone(self.spawn_arguments)
        self.assertIsNone(self.process)
        self.assertEqual(list(self.output_root.rglob("*")), [])

    async def test_spawn_os_error_is_safely_mapped_without_output(self) -> None:
        self.spawn_error = OSError("private executable failure")
        context, _ = self.context()
        with (
            patch(
                "video_app.backends.wan21.adapter._current_repository_revision",
                return_value=WAN21_CODE_REVISION,
            ),
            patch(
                "video_app.backends.wan21.adapter.asyncio.create_subprocess_exec",
                new=self.spawn,
            ),
            self.assertRaises(BackendFailureError) as raised,
        ):
            await self.backend().generate(REQUEST, context)

        self.assertEqual(raised.exception.code, ErrorCode.MODEL_UNAVAILABLE)
        self.assertFalse(raised.exception.retryable)
        self.assertIsNone(self.process)
        self.assertEqual(list(self.output_root.rglob("*")), [])

    async def test_unsupported_settings_fail_before_runtime_or_spawn(self) -> None:
        request = GenerationRequest(
            prompt="private prompt",
            model="unsupported-model",
            resolution=RESOLUTION,
            frame_count=81,
            seed=42,
        )
        context, _ = self.context()
        with (
            patch(
                "video_app.backends.wan21.adapter._current_repository_revision",
                return_value=WAN21_CODE_REVISION,
            ),
            patch(
                "video_app.backends.wan21.adapter.asyncio.create_subprocess_exec",
                new=self.spawn,
            ),
            self.assertRaises(BackendFailureError) as raised,
        ):
            await self.backend().generate(request, context)

        self.assertEqual(raised.exception.code, ErrorCode.UNSUPPORTED_PARAMETERS)
        self.assertFalse(raised.exception.retryable)
        self.assertIsNone(self.spawn_arguments)
        self.assertIsNone(self.process)

    async def test_cancellation_terminates_process_and_removes_candidate(self) -> None:
        self.spawn_returncode = None
        checks = 0

        async def cancellation_requested() -> bool:
            nonlocal checks
            checks += 1
            return checks >= 3

        context, reported = self.context(cancellation_requested)
        with (
            patch(
                "video_app.backends.wan21.adapter._current_repository_revision",
                return_value=WAN21_CODE_REVISION,
            ),
            patch(
                "video_app.backends.wan21.adapter.asyncio.create_subprocess_exec",
                new=self.spawn,
            ),
            self.assertRaises(BackendCancelledError),
        ):
            await self.backend().generate(REQUEST, context)

        assert self.process is not None
        self.assertTrue(self.process.terminated)
        self.assertFalse(self.process.killed)
        self.assertEqual(reported, [])
        self.assertEqual(list(self.output_root.rglob("*")), [])

    async def test_python310_poll_timeout_continues_until_cancellation(self) -> None:
        self.spawn_returncode = None
        checks = 0

        async def cancellation_requested() -> bool:
            nonlocal checks
            checks += 1
            return checks >= 5

        context, _ = self.context(cancellation_requested)
        with (
            patch(
                "video_app.backends.wan21.adapter._current_repository_revision",
                return_value=WAN21_CODE_REVISION,
            ),
            patch(
                "video_app.backends.wan21.adapter.asyncio.create_subprocess_exec",
                new=self.spawn,
            ),
            self.assertRaises(BackendCancelledError),
        ):
            await self.backend().generate(REQUEST, context)

        assert self.process is not None
        self.assertGreaterEqual(checks, 5)
        self.assertTrue(self.process.terminated)
        self.assertEqual(list(self.output_root.rglob("*")), [])

    async def test_termination_timeout_force_kills_process_and_removes_candidate(self) -> None:
        self.spawn_returncode = None
        self.ignore_terminate = True
        checks = 0

        async def cancellation_requested() -> bool:
            nonlocal checks
            checks += 1
            return checks >= 3

        context, _ = self.context(cancellation_requested)
        with (
            patch(
                "video_app.backends.wan21.adapter._current_repository_revision",
                return_value=WAN21_CODE_REVISION,
            ),
            patch(
                "video_app.backends.wan21.adapter.asyncio.create_subprocess_exec",
                new=self.spawn,
            ),
            self.assertRaises(BackendCancelledError),
        ):
            await self.backend().generate(REQUEST, context)

        assert self.process is not None
        self.assertTrue(self.process.terminated)
        self.assertTrue(self.process.killed)
        self.assertEqual(list(self.output_root.rglob("*")), [])

    async def test_second_task_cancellation_waits_for_process_and_output_cleanup(self) -> None:
        self.spawn_returncode = None
        self.ignore_terminate = True
        context, _ = self.context()
        with (
            patch(
                "video_app.backends.wan21.adapter._current_repository_revision",
                return_value=WAN21_CODE_REVISION,
            ),
            patch(
                "video_app.backends.wan21.adapter.asyncio.create_subprocess_exec",
                new=self.spawn,
            ),
        ):
            generation = asyncio.create_task(
                self.backend(termination_grace_seconds=0.2).generate(REQUEST, context)
            )
            while self.process is None:
                await asyncio.sleep(0)
            process = self.process
            generation.cancel()
            await asyncio.wait_for(process.termination_requested.wait(), timeout=1)
            generation.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await generation

        self.assertTrue(process.terminated)
        self.assertTrue(process.killed)
        self.assertEqual(list(self.output_root.rglob("*")), [])


if __name__ == "__main__":
    unittest.main()
