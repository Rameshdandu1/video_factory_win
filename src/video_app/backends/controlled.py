"""Shared fail-closed process boundary for qualified controlled-video runtimes."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import signal
import stat
import subprocess
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from PIL import Image, UnidentifiedImageError

from video_app.domain.models import (
    BackendOutput,
    ConditioningEvidence,
    ControlledVideoOperation,
    ErrorCode,
    GenerationMode,
    GenerationRequest,
    ModelCapability,
    Resolution,
)
from video_app.domain.ports import (
    BackendCancelledError,
    BackendFailureError,
    GenerationContext,
)

_CUDA_PROBE = """\
import json
import torch
if not torch.cuda.is_available():
    print(json.dumps({'cuda': False, 'free_vram': 0}))
else:
    free_vram, _ = torch.cuda.mem_get_info()
    print(json.dumps({'cuda': True, 'free_vram': int(free_vram)}))
"""
_VIDEO_PROBE = """\
import imageio
import json
import sys
reader = imageio.get_reader(sys.argv[1])
count = 0
width = 0
height = 0
try:
    for frame in reader:
        count += 1
        height, width = frame.shape[:2]
finally:
    reader.close()
print(json.dumps({'frames': count, 'width': width, 'height': height}))
"""
_PROMPT_RUNNER = """\
import runpy
import sys
prompt = sys.stdin.read()
sys.argv = [sys.argv[1], *sys.argv[2:], '--prompt', prompt]
runpy.run_path(sys.argv[0], run_name='__main__')
"""
_ENVIRONMENT_ALLOWLIST = frozenset(
    {
        "APPDATA",
        "COMSPEC",
        "CUDA_DEVICE_ORDER",
        "CUDA_HOME",
        "CUDA_PATH",
        "CUDA_VISIBLE_DEVICES",
        "DYLD_LIBRARY_PATH",
        "HF_HOME",
        "HOME",
        "HUGGINGFACE_HUB_CACHE",
        "LD_LIBRARY_PATH",
        "LOCALAPPDATA",
        "NVIDIA_VISIBLE_DEVICES",
        "PATH",
        "PATHEXT",
        "PYTORCH_CUDA_ALLOC_CONF",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "TMPDIR",
        "TORCH_HOME",
        "TRANSFORMERS_CACHE",
        "USERPROFILE",
        "WINDIR",
        "XDG_CACHE_HOME",
    }
)


class ControlledBackendConfigurationError(ValueError):
    """Raised when a configured runtime differs from its reviewed pins."""


def _is_link(path: Path) -> bool:
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return path.is_symlink() or bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _directory(path: Path, field: str) -> Path:
    if not path.is_absolute() or not path.is_dir() or _is_link(path):
        raise ControlledBackendConfigurationError(
            f"{field} must be an existing absolute regular directory"
        )
    return path.resolve(strict=True)


def _file(path: Path, field: str) -> Path:
    if not path.is_absolute() or not path.is_file() or _is_link(path):
        raise ControlledBackendConfigurationError(
            f"{field} must be an existing absolute regular file"
        )
    return path.resolve(strict=True)


def _environment(source: Mapping[str, str] | None = None) -> dict[str, str]:
    values = os.environ if source is None else source
    result = {name: value for name, value in values.items() if name in _ENVIRONMENT_ALLOWLIST}
    result.update(
        {
            "HF_HUB_OFFLINE": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            "TOKENIZERS_PARALLELISM": "false",
            "TRANSFORMERS_OFFLINE": "1",
        }
    )
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _tree_fingerprint(root: Path) -> str:
    entries: list[tuple[str, int, str]] = []
    for current_root, directories, filenames in os.walk(root, followlinks=False):
        directories.sort()
        filenames.sort()
        current = Path(current_root)
        for directory in directories:
            if _is_link(current / directory):
                raise ControlledBackendConfigurationError("runtime trees must not contain links")
        for filename in filenames:
            path = current / filename
            if not path.is_file() or _is_link(path):
                raise ControlledBackendConfigurationError(
                    "runtime tree entries must be regular files"
                )
            entries.append((path.relative_to(root).as_posix(), path.stat().st_size, _sha256(path)))
    if not entries:
        raise ControlledBackendConfigurationError("runtime tree must contain files")
    digest = hashlib.sha256()
    for entry in entries:
        digest.update(json.dumps(entry, separators=(",", ":")).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _repository_revision(root: Path) -> str:
    try:
        revision = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
            env=_environment(),
        ).stdout.strip()
        changed = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
            env=_environment(),
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as error:
        raise ControlledBackendConfigurationError(
            "runtime revision could not be verified"
        ) from error
    if not revision or changed:
        raise ControlledBackendConfigurationError("runtime checkout must be clean and pinned")
    return revision


@dataclass(frozen=True, slots=True)
class ControlledRuntime:
    backend_name: str
    backend_revision: str
    code_revision: str
    model_id: str
    display_name: str
    task: str
    operations: frozenset[ControlledVideoOperation]
    repository_root: Path
    checkpoint_dir: Path
    python_executable: Path
    ffmpeg_executable: Path
    ffmpeg_sha256: str
    ffmpeg_version_line: str
    output_root: Path
    checkpoint_manifest_sha256: str
    resolution: Resolution
    frame_count: int
    input_fps: int
    minimum_free_disk_bytes: int
    minimum_free_vram_bytes: int
    deadline_seconds: int
    cancellation_poll_seconds: float = 0.5
    termination_grace_seconds: float = 10.0

    def __post_init__(self) -> None:
        repository = _directory(self.repository_root, "repository root")
        checkpoint = _directory(self.checkpoint_dir, "checkpoint directory")
        python = _file(self.python_executable, "runtime Python")
        ffmpeg = _file(self.ffmpeg_executable, "FFmpeg executable")
        output = _directory(self.output_root, "output root")
        entry = (
            repository / "vace" / "vace_pipeline.py"
            if self.operations == frozenset({ControlledVideoOperation.VACE_PERFORMANCE_TRANSFER})
            else repository / "generate.py"
        )
        if not entry.is_file() or _is_link(entry):
            raise ControlledBackendConfigurationError("runtime entry point is missing")
        if _repository_revision(repository) != self.code_revision:
            raise ControlledBackendConfigurationError("runtime checkout revision is not approved")
        for value, field in (
            (self.checkpoint_manifest_sha256, "checkpoint manifest"),
            (self.ffmpeg_sha256, "FFmpeg checksum"),
        ):
            if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
                raise ControlledBackendConfigurationError(f"{field} must be lowercase SHA-256")
        if _tree_fingerprint(checkpoint) != self.checkpoint_manifest_sha256:
            raise ControlledBackendConfigurationError("checkpoint files do not match qualification")
        if _sha256(ffmpeg) != self.ffmpeg_sha256:
            raise ControlledBackendConfigurationError(
                "FFmpeg executable does not match qualification"
            )
        try:
            version = subprocess.run(
                [str(ffmpeg), "-version"],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
                env=_environment(),
            ).stdout.splitlines()[0]
        except (OSError, subprocess.SubprocessError, IndexError) as error:
            raise ControlledBackendConfigurationError(
                "FFmpeg version could not be verified"
            ) from error
        if version != self.ffmpeg_version_line:
            raise ControlledBackendConfigurationError("FFmpeg version does not match qualification")
        if (
            min(
                self.frame_count,
                self.input_fps,
                self.minimum_free_disk_bytes,
                self.minimum_free_vram_bytes,
                self.deadline_seconds,
            )
            <= 0
        ):
            raise ControlledBackendConfigurationError("runtime limits must be positive")
        if not self.operations:
            raise ControlledBackendConfigurationError("runtime must enable at least one operation")
        object.__setattr__(self, "repository_root", repository)
        object.__setattr__(self, "checkpoint_dir", checkpoint)
        object.__setattr__(self, "python_executable", python)
        object.__setattr__(self, "ffmpeg_executable", ffmpeg)
        object.__setattr__(self, "output_root", output)


class ControlledVideoBackend:
    """Run one exact reviewed controlled-video operation in an isolated environment."""

    def __init__(self, runtime: ControlledRuntime) -> None:
        self.runtime = runtime

    @property
    def name(self) -> str:
        return self.runtime.backend_name

    @property
    def revision(self) -> str:
        return self.runtime.backend_revision

    def capabilities(self) -> tuple[ModelCapability, ...]:
        return (
            ModelCapability(
                model_id=self.runtime.model_id,
                display_name=self.runtime.display_name,
                modes=frozenset({GenerationMode.IMAGE_TO_VIDEO}),
                resolutions=frozenset({self.runtime.resolution}),
                frame_counts=frozenset({self.runtime.frame_count}),
            ),
        )

    def _supports(self, request: GenerationRequest) -> bool:
        conditioning = request.image_conditioning
        reference = None if conditioning is None else conditioning.reference_video
        return (
            request.model == self.runtime.model_id
            and request.mode is GenerationMode.IMAGE_TO_VIDEO
            and request.resolution == self.runtime.resolution
            and request.frame_count == self.runtime.frame_count
            and conditioning is not None
            and reference is not None
            and reference.operation in self.runtime.operations
            and conditioning.required_backend == self.name
            and conditioning.required_backend_revision == self.revision
        )

    def _child_environment(self) -> dict[str, str]:
        environment = _environment()
        existing = environment.get("PATH")
        environment["PATH"] = str(self.runtime.python_executable.parent) + (
            os.pathsep + existing if existing else ""
        )
        return environment

    def _preflight(self) -> bool:
        if shutil.disk_usage(self.runtime.output_root).free < self.runtime.minimum_free_disk_bytes:
            return False
        try:
            completed = subprocess.run(
                [str(self.runtime.python_executable), "-c", _CUDA_PROBE],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(self.runtime.repository_root),
                env=self._child_environment(),
            )
            payload: Any = json.loads(completed.stdout)
            return (
                bool(payload["cuda"])
                and int(payload["free_vram"]) >= self.runtime.minimum_free_vram_bytes
            )
        except (
            OSError,
            subprocess.SubprocessError,
            ValueError,
            KeyError,
            TypeError,
            json.JSONDecodeError,
        ):
            return False

    async def _stop(self, process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        pid = cast(int | None, getattr(process, "pid", None))
        kill_group = cast(Any, getattr(os, "killpg", None))
        with suppress(ProcessLookupError):
            if os.name != "nt" and pid is not None and kill_group is not None:
                kill_group(pid, signal.SIGTERM)
            else:
                process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=self.runtime.termination_grace_seconds)
            return
        except asyncio.TimeoutError:
            pass
        with suppress(ProcessLookupError):
            signal_kill = cast(int, getattr(signal, "SIGKILL", signal.SIGTERM))
            if os.name != "nt" and pid is not None and kill_group is not None:
                kill_group(pid, signal_kill)
            else:
                process.kill()
        await process.wait()

    async def _run(
        self,
        command: tuple[str, ...],
        context: GenerationContext,
        *,
        stdin: bytes | None = None,
    ) -> None:
        options: dict[str, Any] = (
            {"creationflags": int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))}
            if os.name == "nt"
            else {"start_new_session": True}
        )
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            cwd=str(self.runtime.repository_root),
            env=self._child_environment(),
            **options,
        )
        communicate = asyncio.create_task(process.communicate(stdin))
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.runtime.deadline_seconds
        try:
            while not communicate.done():
                if await context.is_cancellation_requested():
                    raise BackendCancelledError()
                if loop.time() >= deadline:
                    raise BackendFailureError(ErrorCode.GENERATION_FAILED, retryable=True)
                try:
                    await asyncio.wait_for(
                        asyncio.shield(communicate), timeout=self.runtime.cancellation_poll_seconds
                    )
                except asyncio.TimeoutError:
                    continue
            await communicate
            if process.returncode != 0:
                raise BackendFailureError(ErrorCode.GENERATION_FAILED, retryable=True)
        except BaseException:
            await self._stop(process)
            communicate.cancel()
            await asyncio.gather(communicate, return_exceptions=True)
            raise

    async def _trim_reference(
        self, source: Path, destination: Path, start_ms: int, end_ms: int
    ) -> None:
        command = (
            str(self.runtime.ffmpeg_executable),
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(source),
            "-ss",
            f"{start_ms / 1000:.3f}",
            "-t",
            f"{(end_ms - start_ms) / 1000:.3f}",
            "-map",
            "0:v:0",
            "-an",
            "-sn",
            "-dn",
            "-vf",
            f"fps={self.runtime.input_fps},format=yuv420p",
            "-c:v",
            "libx264",
            "-movflags",
            "+faststart",
            "-y",
            str(destination),
        )
        try:
            await asyncio.to_thread(
                subprocess.run,
                command,
                check=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=120,
                env=_environment(),
            )
        except (OSError, subprocess.SubprocessError) as error:
            destination.unlink(missing_ok=True)
            raise BackendFailureError(ErrorCode.GENERATION_FAILED, retryable=False) from error

    def _prepare_image(self, source: Path, destination: Path, request: GenerationRequest) -> str:
        conditioning = request.image_conditioning
        assert conditioning is not None
        try:
            source = _file(source, "starting-frame source")
            checksum = _sha256(source)
            if checksum != conditioning.source_asset_sha256:
                raise BackendFailureError(ErrorCode.GENERATION_FAILED, retryable=False)
            Image.MAX_IMAGE_PIXELS = 40_000_000
            with Image.open(source) as opened:
                opened.load()
                if opened.size != (conditioning.source_width, conditioning.source_height):
                    raise BackendFailureError(ErrorCode.GENERATION_FAILED, retryable=False)
                opened.convert("RGB").save(
                    destination, format="PNG", optimize=False, compress_level=9
                )
            return checksum
        except BackendFailureError:
            raise
        except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as error:
            raise BackendFailureError(ErrorCode.GENERATION_FAILED, retryable=False) from error

    def _vace_command(
        self, request: GenerationRequest, image: Path, video: Path, controls: Path, output: Path
    ) -> tuple[str, ...]:
        return (
            str(self.runtime.python_executable),
            "-c",
            _PROMPT_RUNNER,
            str(self.runtime.repository_root / "vace" / "vace_pipeline.py"),
            "--base",
            "wan",
            "--task",
            "animate_anything",
            "--mode",
            "salientbboxtrack",
            "--video",
            str(video),
            "--image",
            str(image),
            "--pre_save_dir",
            str(controls),
            "--ckpt_dir",
            str(self.runtime.checkpoint_dir),
            "--model_name",
            "vace-1.3B",
            "--size",
            "480p",
            "--frame_num",
            str(request.frame_count),
            "--save_file",
            str(output),
            "--base_seed",
            str(request.seed % (2**64)),
            "--use_prompt_extend",
            "plain",
            "--offload_model",
            "True",
            "--t5_cpu",
        )

    def _animate_preprocess_command(
        self,
        operation: ControlledVideoOperation,
        image: Path,
        video: Path,
        controls: Path,
    ) -> tuple[str, ...]:
        command = [
            str(self.runtime.python_executable),
            str(
                self.runtime.repository_root
                / "wan"
                / "modules"
                / "animate"
                / "preprocess"
                / "preprocess_data.py"
            ),
            "--ckpt_path",
            str(self.runtime.checkpoint_dir / "process_checkpoint"),
            "--video_path",
            str(video),
            "--refer_path",
            str(image),
            "--save_path",
            str(controls),
            "--resolution_area",
            str(self.runtime.resolution.width),
            str(self.runtime.resolution.height),
            "--fps",
            str(self.runtime.input_fps),
        ]
        if operation is ControlledVideoOperation.ANIMATE_CHARACTER:
            command.append("--retarget_flag")
        else:
            command.extend(
                ("--replace_flag", "--iterations", "3", "--k", "7", "--w_len", "1", "--h_len", "1")
            )
        return tuple(command)

    def _animate_command(
        self,
        request: GenerationRequest,
        operation: ControlledVideoOperation,
        controls: Path,
        output: Path,
    ) -> tuple[str, ...]:
        command = [
            str(self.runtime.python_executable),
            "-c",
            _PROMPT_RUNNER,
            str(self.runtime.repository_root / "generate.py"),
            "--task",
            "animate-14B",
            "--ckpt_dir",
            str(self.runtime.checkpoint_dir),
            "--src_root_path",
            str(controls),
            "--refert_num",
            "1",
            "--save_file",
            str(output),
            "--base_seed",
            str(request.seed % (2**64)),
            "--offload_model",
            "True",
            "--convert_model_dtype",
            "--t5_cpu",
        ]
        if operation is ControlledVideoOperation.ANIMATE_REPLACEMENT:
            command.append("--replace_flag")
        return tuple(command)

    async def generate(
        self, request: GenerationRequest, context: GenerationContext
    ) -> BackendOutput:
        if not self._supports(request):
            raise BackendFailureError(ErrorCode.UNSUPPORTED_PARAMETERS, retryable=False)
        if context.resolve_input is None:
            raise BackendFailureError(ErrorCode.GENERATION_FAILED, retryable=False)
        if not self._preflight():
            raise BackendFailureError(ErrorCode.INSUFFICIENT_RESOURCES, retryable=True)
        conditioning = request.image_conditioning
        assert conditioning is not None and conditioning.reference_video is not None
        reference = conditioning.reference_video
        image_source = await context.resolve_input(conditioning.source_storage_key)
        video_source = await context.resolve_input(reference.source_storage_key)
        if _sha256(_file(video_source, "reference-video source")) != reference.source_asset_sha256:
            raise BackendFailureError(ErrorCode.GENERATION_FAILED, retryable=False)
        run_root = self.runtime.output_root / f"controlled-{context.job_id}-{uuid4().hex}"
        run_root.mkdir(mode=0o700)
        image = run_root / "starting-frame.png"
        video = run_root / "reference-trim.mp4"
        controls = run_root / "controls"
        controls.mkdir(mode=0o700)
        output = run_root / "output.mp4"
        candidate = self.runtime.output_root / f"{uuid4().hex}.mp4"
        try:
            image_source_sha = self._prepare_image(image_source, image, request)
            await self._trim_reference(
                video_source, video, reference.trim_start_ms, reference.trim_end_ms
            )
            if reference.operation is ControlledVideoOperation.VACE_PERFORMANCE_TRANSFER:
                await self._run(
                    self._vace_command(request, image, video, controls, output),
                    context,
                    stdin=request.prompt.encode("utf-8"),
                )
            else:
                await self._run(
                    self._animate_preprocess_command(reference.operation, image, video, controls),
                    context,
                )
                await self._run(
                    self._animate_command(request, reference.operation, controls, output),
                    context,
                    stdin=request.prompt.encode("utf-8"),
                )
            try:
                probed = await asyncio.to_thread(
                    subprocess.run,
                    [str(self.runtime.python_executable), "-c", _VIDEO_PROBE, str(output)],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    cwd=str(self.runtime.repository_root),
                    env=self._child_environment(),
                )
                metadata = json.loads(probed.stdout)
                resolution = Resolution(int(metadata["width"]), int(metadata["height"]))
                frame_count = int(metadata["frames"])
            except (
                OSError,
                subprocess.SubprocessError,
                ValueError,
                KeyError,
                TypeError,
                json.JSONDecodeError,
            ) as error:
                raise BackendFailureError(ErrorCode.GENERATION_FAILED, retryable=True) from error
            if resolution != request.resolution or frame_count != request.frame_count:
                raise BackendFailureError(ErrorCode.GENERATION_FAILED, retryable=True)
            evidence = ConditioningEvidence(
                source_sha256=image_source_sha,
                derivative_sha256=_sha256(image),
                derivative_width=conditioning.source_width,
                derivative_height=conditioning.source_height,
                reference_source_sha256=reference.source_asset_sha256,
                reference_derivative_sha256=_sha256(video),
                control_fingerprint=_tree_fingerprint(controls),
            )
            image.unlink(missing_ok=True)
            video.unlink(missing_ok=True)
            shutil.rmtree(controls)
            os.replace(output, candidate)
            shutil.rmtree(run_root)
            return BackendOutput(
                temporary_path=candidate,
                resolution=resolution,
                frame_count=frame_count,
                duration_seconds=None,
                conditioning_evidence=evidence,
            )
        except BaseException:
            candidate.unlink(missing_ok=True)
            shutil.rmtree(run_root, ignore_errors=True)
            raise
