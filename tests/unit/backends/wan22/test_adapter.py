from __future__ import annotations

import hashlib
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from video_app.backends.wan22.adapter import (
    WAN22_BACKEND_REVISION,
    WAN22_CODE_REVISION,
    WAN22_MODEL_ID,
    Wan22Backend,
    Wan22ConfigurationError,
)
from video_app.domain.models import (
    ErrorCode,
    GenerationMode,
    GenerationRequest,
    ImageConditioning,
    Resolution,
)
from video_app.domain.ports import BackendFailureError, GenerationContext


def _box(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", len(payload) + 8, kind) + payload


MP4 = (
    _box(b"ftyp", b"isom\x00\x00\x02\x00isomiso2") + _box(b"moov", b"\x00") + _box(b"mdat", b"\x00")
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _argument(arguments: tuple[str, ...], name: str) -> str:
    return arguments[arguments.index(name) + 1]


class FakeProcess:
    returncode = 0

    async def wait(self) -> int:
        return 0

    async def communicate(self, input: bytes | None = None) -> tuple[bytes, bytes]:
        del input
        return b"", b""

    def terminate(self) -> None:
        return None

    def kill(self) -> None:
        return None


class Wan22BackendTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name).resolve()
        self.repository = root / "Wan2.2"
        self.checkpoint = root / "checkpoint"
        self.output = root / "output"
        self.assets = root / "assets"
        for path in (self.repository, self.checkpoint, self.output, self.assets):
            path.mkdir()
        (self.repository / "generate.py").write_text("# fixture\n", encoding="utf-8")
        weights = self.checkpoint / "weights.bin"
        weights.write_bytes(b"qualified fixture weights")
        entry = json.dumps(
            ["weights.bin", weights.stat().st_size, _sha256(weights)], separators=(",", ":")
        ).encode("utf-8")
        self.checkpoint_digest = hashlib.sha256(entry + b"\n").hexdigest()
        self.source = self.assets / "approved.png"
        Image.new("RGBA", (832, 480), (40, 80, 120, 200)).save(self.source, format="PNG")
        self.arguments: tuple[str, ...] | None = None

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def backend(self) -> Wan22Backend:
        return Wan22Backend(
            repository_root=self.repository,
            checkpoint_dir=self.checkpoint,
            python_executable=Path(sys.executable).resolve(),
            output_root=self.output,
            checkpoint_manifest_sha256=self.checkpoint_digest,
            minimum_free_disk_bytes=1,
            minimum_free_vram_bytes=1,
            cancellation_poll_seconds=0.001,
            termination_grace_seconds=0.01,
        )

    def request(self, source: Path | None = None) -> GenerationRequest:
        selected = self.source if source is None else source
        conditioning = ImageConditioning(
            owner_id="owner",
            project_id="project",
            shot_id="shot",
            shot_version=2,
            composition_id="composition",
            composition_revision=1,
            composition_fingerprint="b" * 64,
            source_asset_id="asset",
            source_asset_version=1,
            source_asset_sha256=_sha256(selected),
            source_storage_key="uploads/approved.png",
            source_width=832,
            source_height=480,
            required_backend="wan22-ti2v",
            required_backend_revision=WAN22_BACKEND_REVISION,
            manifest_fingerprint="c" * 64,
        )
        return GenerationRequest(
            prompt="private prompt",
            model=WAN22_MODEL_ID,
            resolution=Resolution(1280, 704),
            frame_count=81,
            seed=-1,
            mode=GenerationMode.IMAGE_TO_VIDEO,
            image_conditioning=conditioning,
        )

    def context(self, source: Path | None = None) -> GenerationContext:
        selected = self.source if source is None else source

        async def report(_: object) -> None:
            return None

        async def cancelled() -> bool:
            return False

        async def resolve(key: str) -> Path:
            self.assertEqual(key, "uploads/approved.png")
            return selected

        return GenerationContext("job", report, cancelled, resolve)

    async def spawn(self, *arguments: object, **_: object) -> FakeProcess:
        self.arguments = tuple(str(value) for value in arguments)
        Path(_argument(self.arguments, "--save_file")).write_bytes(MP4)
        return FakeProcess()

    async def test_approved_image_is_normalized_and_plumbed_to_upstream_image_argument(
        self,
    ) -> None:
        with (
            patch(
                "video_app.backends.wan22.adapter._current_repository_revision",
                return_value=WAN22_CODE_REVISION,
            ),
            patch.object(Wan22Backend, "_preflight", return_value=True),
            patch(
                "video_app.backends.wan22.adapter.asyncio.create_subprocess_exec",
                new=self.spawn,
            ),
        ):
            output = await self.backend().generate(self.request(), self.context())

        assert self.arguments is not None
        image_path = Path(_argument(self.arguments, "--image"))
        self.assertTrue(image_path.is_relative_to(self.output))
        self.assertFalse(
            image_path.exists(), "normalized derivative must be cleaned after execution"
        )
        self.assertEqual(_argument(self.arguments, "--task"), "ti2v-5B")
        self.assertEqual(_argument(self.arguments, "--size"), "1280*704")
        self.assertEqual(_argument(self.arguments, "--base_seed"), str(2**64 - 1))
        self.assertIn("--convert_model_dtype", self.arguments)
        self.assertIn("--t5_cpu", self.arguments)
        assert output.conditioning_evidence is not None
        self.assertEqual(output.conditioning_evidence.source_sha256, _sha256(self.source))
        self.assertNotEqual(
            output.conditioning_evidence.derivative_sha256,
            output.conditioning_evidence.source_sha256,
        )
        self.assertEqual(output.resolution, Resolution(1248, 704))
        output.temporary_path.unlink()

    async def test_hash_mismatch_fails_before_process_and_never_falls_back_to_t2v(self) -> None:
        changed = self.assets / "changed.png"
        Image.new("RGB", (832, 480), (200, 10, 10)).save(changed, format="PNG")
        with (
            patch(
                "video_app.backends.wan22.adapter._current_repository_revision",
                return_value=WAN22_CODE_REVISION,
            ),
            patch.object(Wan22Backend, "_preflight", return_value=True),
            patch(
                "video_app.backends.wan22.adapter.asyncio.create_subprocess_exec",
                new=self.spawn,
            ),
            self.assertRaises(BackendFailureError) as raised,
        ):
            await self.backend().generate(self.request(), self.context(changed))

        self.assertEqual(raised.exception.code, ErrorCode.GENERATION_FAILED)
        self.assertIsNone(self.arguments)
        self.assertEqual(list(self.output.iterdir()), [])

    async def test_missing_worker_input_resolver_is_rejected(self) -> None:
        context = self.context()
        context = GenerationContext(
            context.job_id,
            context.report_progress,
            context.is_cancellation_requested,
        )
        with (
            patch(
                "video_app.backends.wan22.adapter._current_repository_revision",
                return_value=WAN22_CODE_REVISION,
            ),
            self.assertRaises(BackendFailureError) as raised,
        ):
            await self.backend().generate(self.request(), context)
        self.assertEqual(raised.exception.code, ErrorCode.UNSUPPORTED_PARAMETERS)

    def test_checkpoint_bytes_must_match_the_qualified_manifest(self) -> None:
        (self.checkpoint / "weights.bin").write_bytes(b"changed after qualification")
        with (
            patch(
                "video_app.backends.wan22.adapter._current_repository_revision",
                return_value=WAN22_CODE_REVISION,
            ),
            self.assertRaisesRegex(Wan22ConfigurationError, "qualified manifest"),
        ):
            self.backend()


if __name__ == "__main__":
    unittest.main()
