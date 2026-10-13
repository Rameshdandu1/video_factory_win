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

from video_app.backends.animate import (
    ANIMATE_BACKEND_REVISION,
    ANIMATE_CODE_REVISION,
    ANIMATE_MODEL_ID,
    ANIMATE_MODEL_REVISION,
    ANIMATE_TASK,
    WanAnimateBackend,
)
from video_app.backends.controlled import ControlledRuntime, ControlledVideoBackend
from video_app.backends.vace import (
    VACE_BACKEND_REVISION,
    VACE_CODE_REVISION,
    VACE_MODEL_ID,
    VACE_MODEL_REVISION,
    VACE_TASK,
    VaceBackend,
)
from video_app.domain.models import (
    BackendOutput,
    ControlledVideoOperation,
    GenerationMode,
    GenerationRequest,
    ImageConditioning,
    ReferenceVideoConditioning,
    Resolution,
)
from video_app.domain.ports import BackendCancelledError, GenerationContext

_RUN = os.environ.get("VIDEO_APP_RUN_CONTROLLED_GPU_TESTS") == "1"


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise AssertionError(f"{name} must be configured")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _request(
    *,
    runtime: ControlledRuntime,
    image: Path,
    video: Path,
    operation: ControlledVideoOperation,
    trim_end_ms: int,
    identifier: str,
) -> GenerationRequest:
    with Image.open(image) as opened:
        width, height = opened.size
    plan = hashlib.sha256(f"{operation.value}:{trim_end_ms}".encode()).hexdigest()
    reference = ReferenceVideoConditioning(
        guidance_id=f"guidance-{identifier}",
        guidance_revision=1,
        guidance_fingerprint=hashlib.sha256(f"guidance:{identifier}".encode()).hexdigest(),
        purpose="motion_performance",
        source_asset_id="qualification-video",
        source_asset_version=1,
        source_asset_sha256=_sha256(video),
        source_storage_key="qualification/video.mp4",
        trim_start_ms=0,
        trim_end_ms=trim_end_ms,
        operation=operation,
        preserve_environment=operation is ControlledVideoOperation.VACE_PERFORMANCE_TRANSFER,
        constraint_plan_fingerprint=plan,
    )
    conditioning = ImageConditioning(
        owner_id="qualification",
        project_id="qualification",
        shot_id=identifier,
        shot_version=1,
        composition_id=f"composition-{identifier}",
        composition_revision=1,
        composition_fingerprint=hashlib.sha256(f"composition:{identifier}".encode()).hexdigest(),
        source_asset_id="qualification-image",
        source_asset_version=1,
        source_asset_sha256=_sha256(image),
        source_storage_key="qualification/image.png",
        source_width=width,
        source_height=height,
        required_backend=runtime.backend_name,
        required_backend_revision=runtime.backend_revision,
        manifest_fingerprint=hashlib.sha256(f"manifest:{identifier}:{plan}".encode()).hexdigest(),
        reference_video=reference,
    )
    return GenerationRequest(
        prompt="A natural performance with stable framing and no unrequested emotional claim",
        model=runtime.model_id,
        resolution=runtime.resolution,
        frame_count=runtime.frame_count,
        seed=42,
        mode=GenerationMode.IMAGE_TO_VIDEO,
        image_conditioning=conditioning,
    )


@pytest.mark.gpu
@pytest.mark.integration
@unittest.skipUnless(
    _RUN,
    "set VIDEO_APP_RUN_CONTROLLED_GPU_TESTS=1 for explicit VACE/Animate qualification",
)
class ControlledVideoGpuQualificationTests(unittest.IsolatedAsyncioTestCase):
    async def test_provider_operations_and_cancellation_produce_evidence(self) -> None:
        provider = _required("VIDEO_APP_CONTROLLED_QUALIFICATION_PROVIDER")
        if provider not in {"vace", "animate"}:
            self.fail("VIDEO_APP_CONTROLLED_QUALIFICATION_PROVIDER must be vace or animate")
        prefix = "VIDEO_APP_VACE" if provider == "vace" else "VIDEO_APP_WAN_ANIMATE"
        repository = Path(_required(f"{prefix}_REPOSITORY_ROOT")).resolve(strict=True)
        checkpoint = Path(_required(f"{prefix}_CHECKPOINT_DIR")).resolve(strict=True)
        python = Path(_required(f"{prefix}_PYTHON")).resolve(strict=True)
        image = Path(_required("VIDEO_APP_CONTROLLED_QUALIFICATION_IMAGE")).resolve(strict=True)
        video = Path(_required("VIDEO_APP_CONTROLLED_QUALIFICATION_VIDEO")).resolve(strict=True)
        report_dir = Path(_required("VIDEO_APP_CONTROLLED_QUALIFICATION_DIR")).resolve(strict=True)
        ffmpeg = Path(_required("VIDEO_APP_CONTROLLED_FFMPEG_EXECUTABLE")).resolve(strict=True)
        checkpoint_digest = _required(f"{prefix}_CHECKPOINT_MANIFEST_SHA256")
        ffmpeg_digest = _required("VIDEO_APP_CONTROLLED_FFMPEG_SHA256")
        ffmpeg_version = _required("VIDEO_APP_CONTROLLED_FFMPEG_VERSION_LINE")
        minimum_disk = int(_required("VIDEO_APP_CONTROLLED_MINIMUM_FREE_DISK_BYTES"))
        minimum_vram = int(_required("VIDEO_APP_CONTROLLED_MINIMUM_FREE_VRAM_BYTES"))
        trim_end_ms = int(_required("VIDEO_APP_CONTROLLED_QUALIFICATION_TRIM_END_MS"))
        cancel_after = float(os.environ.get("VIDEO_APP_CONTROLLED_CANCEL_AFTER_SECONDS", "5"))
        self.assertEqual(_sha256(ffmpeg), ffmpeg_digest)

        operations: tuple[ControlledVideoOperation, ...]
        if provider == "vace":
            operations = (ControlledVideoOperation.VACE_PERFORMANCE_TRANSFER,)
            code_revision = VACE_CODE_REVISION
            model_revision = VACE_MODEL_REVISION
            model_id = VACE_MODEL_ID
            backend_revision = VACE_BACKEND_REVISION
            task = VACE_TASK
            resolution = Resolution(832, 480)
            frame_count = 81
            input_fps = 16
        else:
            operations = (
                ControlledVideoOperation.ANIMATE_CHARACTER,
                ControlledVideoOperation.ANIMATE_REPLACEMENT,
            )
            code_revision = ANIMATE_CODE_REVISION
            model_revision = ANIMATE_MODEL_REVISION
            model_id = ANIMATE_MODEL_ID
            backend_revision = ANIMATE_BACKEND_REVISION
            task = ANIMATE_TASK
            resolution = Resolution(1280, 720)
            frame_count = 77
            input_fps = 30

        with tempfile.TemporaryDirectory(
            dir=report_dir, prefix=f"{provider}-qualification-"
        ) as name:
            output_root = Path(name).resolve(strict=True)
            runtime = ControlledRuntime(
                backend_name="vace-wan21" if provider == "vace" else "wan22-animate",
                backend_revision=backend_revision,
                code_revision=code_revision,
                model_id=model_id,
                display_name=f"{provider} qualification",
                task=task,
                operations=frozenset(operations),
                repository_root=repository,
                checkpoint_dir=checkpoint,
                python_executable=python,
                ffmpeg_executable=ffmpeg,
                ffmpeg_sha256=ffmpeg_digest,
                ffmpeg_version_line=ffmpeg_version,
                output_root=output_root,
                checkpoint_manifest_sha256=checkpoint_digest,
                resolution=resolution,
                frame_count=frame_count,
                input_fps=input_fps,
                minimum_free_disk_bytes=minimum_disk,
                minimum_free_vram_bytes=minimum_vram,
                deadline_seconds=7_200,
            )
            backend: ControlledVideoBackend = (
                VaceBackend(runtime) if provider == "vace" else WanAnimateBackend(runtime)
            )

            async def run(operation: ControlledVideoOperation, identifier: str) -> BackendOutput:
                async def report(_: object) -> None:
                    return None

                async def not_cancelled() -> bool:
                    return False

                async def resolve(storage_key: str) -> Path:
                    return image if storage_key.endswith("image.png") else video

                return await backend.generate(
                    _request(
                        runtime=runtime,
                        image=image,
                        video=video,
                        operation=operation,
                        trim_end_ms=trim_end_ms,
                        identifier=identifier,
                    ),
                    GenerationContext(identifier, report, not_cancelled, resolve),
                )

            outputs = []
            for operation in operations:
                output = await run(operation, operation.value)
                assert output.conditioning_evidence is not None
                evidence = output.conditioning_evidence
                self.assertEqual(evidence.source_sha256, _sha256(image))
                self.assertEqual(evidence.reference_source_sha256, _sha256(video))
                self.assertIsNotNone(evidence.reference_derivative_sha256)
                self.assertIsNotNone(evidence.control_fingerprint)
                outputs.append(output)

            cancel = asyncio.Event()

            async def report(_: object) -> None:
                return None

            async def cancelled() -> bool:
                return cancel.is_set()

            async def resolve(storage_key: str) -> Path:
                return image if storage_key.endswith("image.png") else video

            cancellation = asyncio.create_task(
                backend.generate(
                    _request(
                        runtime=runtime,
                        image=image,
                        video=video,
                        operation=operations[0],
                        trim_end_ms=trim_end_ms,
                        identifier="cancel",
                    ),
                    GenerationContext("cancel", report, cancelled, resolve),
                )
            )
            await asyncio.sleep(cancel_after)
            cancel.set()
            with self.assertRaises(BackendCancelledError):
                await asyncio.wait_for(cancellation, timeout=120)
            self.assertEqual(list(output_root.glob("controlled-cancel-*")), [])

            report_payload = {
                "schema_version": "controlled-video-qualification-v1",
                "status": "approved",
                "approved_at": datetime.now(timezone.utc).isoformat(),
                "code_revision": code_revision,
                "model_revision": model_revision,
                "task": task,
                "checkpoint_manifest_sha256": checkpoint_digest,
                "ffmpeg_sha256": ffmpeg_digest,
                "ffmpeg_version_line": ffmpeg_version,
                "operations": [operation.value for operation in operations],
                "minimum_free_disk_bytes": minimum_disk,
                "minimum_free_vram_bytes": minimum_vram,
                "starting_frame_conditioning_verified": True,
                "reference_video_trim_verified": True,
                "constraint_plan_verified": True,
                "control_derivatives_verified": True,
                "cancellation_cleanup_verified": True,
                "evidence": [
                    {
                        "operation": operation.value,
                        "image_source_sha256": output.conditioning_evidence.source_sha256,
                        "image_derivative_sha256": output.conditioning_evidence.derivative_sha256,
                        "reference_source_sha256": (
                            output.conditioning_evidence.reference_source_sha256
                        ),
                        "reference_derivative_sha256": (
                            output.conditioning_evidence.reference_derivative_sha256
                        ),
                        "control_fingerprint": output.conditioning_evidence.control_fingerprint,
                    }
                    for operation, output in zip(operations, outputs, strict=True)
                    if output.conditioning_evidence is not None
                ],
            }
            target = report_dir / f"{provider}-qualification.json"
            partial = report_dir / f".{provider}-qualification.part"
            partial.write_text(
                json.dumps(report_payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            os.replace(partial, target)
            for output in outputs:
                output.temporary_path.unlink()


if __name__ == "__main__":
    unittest.main()
