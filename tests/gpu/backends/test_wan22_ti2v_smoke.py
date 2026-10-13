from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import pytest
from PIL import Image

from video_app.backends.wan22 import (
    WAN22_BACKEND_REVISION,
    WAN22_CODE_REVISION,
    WAN22_MODEL_ID,
    WAN22_MODEL_REVISION,
    Wan22Backend,
)
from video_app.domain.models import (
    BackendOutput,
    GenerationMode,
    GenerationRequest,
    ImageConditioning,
    Resolution,
)
from video_app.domain.ports import BackendCancelledError, GenerationContext

_RUN = os.environ.get("VIDEO_APP_RUN_WAN22_GPU_TESTS") == "1"


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise AssertionError(f"{name} must be configured")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _request(path: Path, identifier: str) -> GenerationRequest:
    with Image.open(path) as image:
        width, height = image.size
    digest = _sha256(path)
    return GenerationRequest(
        prompt="A subject makes a small natural movement while identity and framing stay stable",
        model=WAN22_MODEL_ID,
        resolution=Resolution(1280, 704),
        frame_count=81,
        seed=42,
        mode=GenerationMode.IMAGE_TO_VIDEO,
        image_conditioning=ImageConditioning(
            owner_id="qualification",
            project_id="qualification",
            shot_id=identifier,
            shot_version=1,
            composition_id=identifier,
            composition_revision=1,
            composition_fingerprint=hashlib.sha256(identifier.encode()).hexdigest(),
            source_asset_id=identifier,
            source_asset_version=1,
            source_asset_sha256=digest,
            source_storage_key=f"uploads/{identifier}.png",
            source_width=width,
            source_height=height,
            required_backend="wan22-ti2v",
            required_backend_revision=WAN22_BACKEND_REVISION,
            manifest_fingerprint=hashlib.sha256((identifier + digest).encode()).hexdigest(),
        ),
    )


@pytest.mark.gpu
@pytest.mark.integration
@unittest.skipUnless(
    _RUN,
    "set VIDEO_APP_RUN_WAN22_GPU_TESTS=1 for explicit Wan2.2 TI2V qualification",
)
class Wan22GpuQualificationTests(unittest.IsolatedAsyncioTestCase):
    async def test_two_inputs_and_cancellation_produce_qualification_evidence(self) -> None:
        repository = Path(_required("VIDEO_APP_WAN22_REPOSITORY_ROOT")).resolve(strict=True)
        checkpoint = Path(_required("VIDEO_APP_WAN22_CHECKPOINT_DIR")).resolve(strict=True)
        python = Path(_required("VIDEO_APP_WAN22_PYTHON")).resolve(strict=True)
        input_a = Path(_required("VIDEO_APP_WAN22_QUALIFICATION_INPUT_A")).resolve(strict=True)
        input_b = Path(_required("VIDEO_APP_WAN22_QUALIFICATION_INPUT_B")).resolve(strict=True)
        report_dir = Path(_required("VIDEO_APP_WAN22_QUALIFICATION_DIR")).resolve(strict=True)
        checkpoint_digest = _required("VIDEO_APP_WAN22_CHECKPOINT_MANIFEST_SHA256")
        minimum_disk = int(_required("VIDEO_APP_WAN22_MINIMUM_FREE_DISK_BYTES"))
        minimum_vram = int(_required("VIDEO_APP_WAN22_MINIMUM_FREE_VRAM_BYTES"))
        self.assertNotEqual(_sha256(input_a), _sha256(input_b))

        with tempfile.TemporaryDirectory(dir=report_dir, prefix="wan22-qualification-") as name:
            output_root = Path(name).resolve(strict=True)
            backend = Wan22Backend(
                repository_root=repository,
                checkpoint_dir=checkpoint,
                python_executable=python,
                output_root=output_root,
                checkpoint_manifest_sha256=checkpoint_digest,
                minimum_free_disk_bytes=minimum_disk,
                minimum_free_vram_bytes=minimum_vram,
            )

            async def run(source: Path, identifier: str) -> BackendOutput:
                async def report(_: object) -> None:
                    return None

                async def not_cancelled() -> bool:
                    return False

                async def resolve(_: str) -> Path:
                    return source

                return await backend.generate(
                    _request(source, identifier),
                    GenerationContext(identifier, report, not_cancelled, resolve),
                )

            first = await run(input_a, "input-a")
            second = await run(input_b, "input-b")
            assert first.conditioning_evidence is not None
            assert second.conditioning_evidence is not None
            self.assertNotEqual(
                first.conditioning_evidence.derivative_sha256,
                second.conditioning_evidence.derivative_sha256,
            )

            cancel = asyncio.Event()

            async def report(_: object) -> None:
                return None

            async def cancelled() -> bool:
                return cancel.is_set()

            async def resolve(_: str) -> Path:
                return input_a

            cancellation = asyncio.create_task(
                backend.generate(
                    _request(input_a, "cancel"),
                    GenerationContext("cancel", report, cancelled, resolve),
                )
            )
            await asyncio.sleep(5)
            cancel.set()
            with self.assertRaises(BackendCancelledError):
                await asyncio.wait_for(cancellation, timeout=120)
            self.assertEqual(list(output_root.glob("*.conditioning.png")), [])

            report_payload = {
                "schema_version": "wan22-ti2v-qualification-v1",
                "status": "approved",
                "approved_at": datetime.now(timezone.utc).isoformat(),
                "code_revision": WAN22_CODE_REVISION,
                "model_revision": WAN22_MODEL_REVISION,
                "task": "ti2v-5B",
                "checkpoint_manifest_sha256": checkpoint_digest,
                "minimum_free_disk_bytes": minimum_disk,
                "minimum_free_vram_bytes": minimum_vram,
                "input_conditioning_verified": True,
                "no_t2v_fallback_verified": True,
                "cancellation_cleanup_verified": True,
                "inputs": [
                    first.conditioning_evidence.source_sha256,
                    second.conditioning_evidence.source_sha256,
                ],
                "derivatives": [
                    first.conditioning_evidence.derivative_sha256,
                    second.conditioning_evidence.derivative_sha256,
                ],
            }
            target = report_dir / "wan22-ti2v-qualification.json"
            partial = report_dir / ".wan22-ti2v-qualification.part"
            partial.write_text(
                json.dumps(report_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            os.replace(partial, target)
            first.temporary_path.unlink()
            second.temporary_path.unlink()


if __name__ == "__main__":
    unittest.main()
