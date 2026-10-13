"""Fail-closed subprocess adapter for pinned Wan2.2 TI2V image generation."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import signal
import stat
import struct
import subprocess
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar, cast
from uuid import uuid4

from PIL import Image, UnidentifiedImageError

from video_app.domain.models import (
    BackendOutput,
    ConditioningEvidence,
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

WAN22_CODE_REVISION = "1ea34ff48f87168174e12956e200b1d908b1c5ff"
WAN22_MODEL_REVISION = "921dbaf3f1674a56f47e83fb80a34bac8a8f203e"
WAN22_MODEL_ID = "wan22-ti2v-5b"
WAN22_TASK = "ti2v-5B"
WAN22_BACKEND_REVISION = (
    f"wan2.2@{WAN22_CODE_REVISION};task={WAN22_TASK};model@{WAN22_MODEL_REVISION}"
)
WAN22_AREA_PRESETS = frozenset({Resolution(1280, 704), Resolution(704, 1280)})
WAN22_FRAME_COUNTS = frozenset({81})

_PROMPT_RUNNER = """\
import imageio
import runpy
import sys

arguments = sys.argv[1:]

def pop_value(name):
    index = arguments.index(name)
    value = arguments[index + 1]
    del arguments[index:index + 2]
    return value

output_path = arguments[arguments.index('--save_file') + 1]
expected_width = int(pop_value('--video-app-expected-width'))
expected_height = int(pop_value('--video-app-expected-height'))
expected_frames = int(arguments[arguments.index('--frame_num') + 1])
if '--image' not in arguments:
    raise RuntimeError('image conditioning is required')
prompt = sys.stdin.read()
sys.argv = ['generate.py', *arguments, '--prompt', prompt]
runpy.run_path('generate.py', run_name='__main__')

reader = imageio.get_reader(output_path)
decoded_frames = 0
try:
    for frame in reader:
        decoded_frames += 1
        if decoded_frames > expected_frames:
            raise RuntimeError('generated video has too many frames')
        if tuple(frame.shape[:2]) != (expected_height, expected_width):
            raise RuntimeError('generated video has the wrong resolution')
finally:
    reader.close()
if decoded_frames != expected_frames:
    raise RuntimeError('generated video has the wrong frame count')
"""
_CUDA_PROBE = """\
import json
import torch

if not torch.cuda.is_available():
    print(json.dumps({'cuda': False, 'free_vram': 0}))
else:
    free_vram, _ = torch.cuda.mem_get_info()
    print(json.dumps({'cuda': True, 'free_vram': int(free_vram)}))
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
_TaskResult = TypeVar("_TaskResult")


class Wan22ConfigurationError(ValueError):
    """Raised when the external Wan2.2 runtime does not match its qualification."""


def _is_link_or_reparse_point(path: Path) -> bool:
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return path.is_symlink() or bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _resolve_existing_directory(path: Path, field: str) -> Path:
    if not path.is_absolute() or not path.is_dir() or _is_link_or_reparse_point(path):
        raise Wan22ConfigurationError(f"{field} must be an existing absolute regular directory")
    return path.resolve(strict=True)


def _resolve_existing_file(path: Path, field: str) -> Path:
    if not path.is_absolute() or not path.is_file() or _is_link_or_reparse_point(path):
        raise Wan22ConfigurationError(f"{field} must be an existing absolute regular file")
    return path.resolve(strict=True)


def _safe_environment(source: Mapping[str, str] | None = None) -> dict[str, str]:
    values = os.environ if source is None else source
    environment = {name: value for name, value in values.items() if name in _ENVIRONMENT_ALLOWLIST}
    environment.update(
        {
            "HF_HUB_OFFLINE": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            "TOKENIZERS_PARALLELISM": "false",
            "TRANSFORMERS_OFFLINE": "1",
        }
    )
    return environment


def _current_repository_revision(repository_root: Path) -> str:
    try:
        revision = subprocess.run(
            ["git", "-C", str(repository_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
            env=_safe_environment(),
        ).stdout.strip()
        changed = subprocess.run(
            ["git", "-C", str(repository_root), "status", "--porcelain", "--untracked-files=all"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
            env=_safe_environment(),
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as error:
        raise Wan22ConfigurationError("Wan2.2 repository revision could not be verified") from error
    if not revision or changed:
        raise Wan22ConfigurationError("Wan2.2 checkout must be clean and revision-pinned")
    return revision


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _checkpoint_manifest_sha256(root: Path) -> str:
    entries: list[tuple[str, int, str]] = []
    for current_root, directories, filenames in os.walk(root, followlinks=False):
        directories.sort()
        filenames.sort()
        current = Path(current_root)
        for directory in directories:
            if _is_link_or_reparse_point(current / directory):
                raise Wan22ConfigurationError("checkpoint directories must not contain links")
        for filename in filenames:
            path = current / filename
            if not path.is_file() or _is_link_or_reparse_point(path):
                raise Wan22ConfigurationError("checkpoint entries must be regular files")
            entries.append((path.relative_to(root).as_posix(), path.stat().st_size, _sha256(path)))
    if not entries:
        raise Wan22ConfigurationError("checkpoint directory must contain pinned files")
    digest = hashlib.sha256()
    for relative, size, checksum in entries:
        digest.update(json.dumps([relative, size, checksum], separators=(",", ":")).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _best_output_size(width: int, height: int, max_area: int) -> Resolution:
    """Pinned upstream TI2V aspect-preserving 32-pixel geometry rule."""
    ratio = width / height
    output_width = (max_area * ratio) ** 0.5
    output_height = max_area / output_width
    width_first = max(32, int(output_width // 32 * 32))
    height_from_width = max(32, int(max_area / width_first // 32 * 32))
    height_first = max(32, int(output_height // 32 * 32))
    width_from_height = max(32, int(max_area / height_first // 32 * 32))
    first_error = abs(width_first / height_from_width - ratio)
    second_error = abs(width_from_height / height_first - ratio)
    if first_error <= second_error:
        return Resolution(width_first, height_from_width)
    return Resolution(width_from_height, height_first)


def _prepare_input(
    source: Path, request: GenerationRequest, destination: Path
) -> ConditioningEvidence:
    manifest = request.image_conditioning
    if manifest is None:
        raise BackendFailureError(ErrorCode.UNSUPPORTED_PARAMETERS, retryable=False)
    try:
        source = _resolve_existing_file(source, "conditioning image")
        source_sha256 = _sha256(source)
        if source_sha256 != manifest.source_asset_sha256:
            raise BackendFailureError(ErrorCode.GENERATION_FAILED, retryable=False)
        Image.MAX_IMAGE_PIXELS = 40_000_000
        with Image.open(source) as opened:
            opened.load()
            if opened.format not in {"PNG", "JPEG", "WEBP"}:
                raise BackendFailureError(ErrorCode.UNSUPPORTED_PARAMETERS, retryable=False)
            if opened.size != (manifest.source_width, manifest.source_height):
                raise BackendFailureError(ErrorCode.GENERATION_FAILED, retryable=False)
            image = opened.convert("RGB")
            image.save(destination, format="PNG", optimize=False, compress_level=9)
        return ConditioningEvidence(
            source_sha256=source_sha256,
            derivative_sha256=_sha256(destination),
            derivative_width=manifest.source_width,
            derivative_height=manifest.source_height,
        )
    except BackendFailureError:
        raise
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as error:
        raise BackendFailureError(ErrorCode.GENERATION_FAILED, retryable=False) from error


def _validate_mp4(path: Path) -> None:
    if not path.is_absolute() or not path.is_file() or _is_link_or_reparse_point(path):
        raise BackendFailureError(ErrorCode.GENERATION_FAILED, retryable=True)
    size = path.stat().st_size
    if path.suffix.lower() != ".mp4" or size <= 24:
        raise BackendFailureError(ErrorCode.GENERATION_FAILED, retryable=True)
    boxes: dict[bytes, int] = {}
    offset = 0
    with path.open("rb") as generated:
        while offset < size:
            generated.seek(offset)
            header = generated.read(8)
            if len(header) != 8:
                raise BackendFailureError(ErrorCode.GENERATION_FAILED, retryable=True)
            box_size, kind = struct.unpack(">I4s", header)
            header_size = 8
            if box_size == 1:
                raw = generated.read(8)
                if len(raw) != 8:
                    raise BackendFailureError(ErrorCode.GENERATION_FAILED, retryable=True)
                box_size = struct.unpack(">Q", raw)[0]
                header_size = 16
            elif box_size == 0:
                box_size = size - offset
            if box_size < header_size or offset + box_size > size:
                raise BackendFailureError(ErrorCode.GENERATION_FAILED, retryable=True)
            boxes[kind] = box_size - header_size
            offset += box_size
    if boxes.get(b"ftyp") is None or boxes.get(b"moov", 0) <= 0 or boxes.get(b"mdat", 0) <= 0:
        raise BackendFailureError(ErrorCode.GENERATION_FAILED, retryable=True)


def _taskkill_windows_process_tree(process_id: int, timeout_seconds: float) -> bool:
    system_root = os.environ.get("SYSTEMROOT")
    executable = Path(system_root or "") / "System32" / "taskkill.exe"
    if not executable.is_absolute() or not executable.is_file():
        return False
    try:
        completed = subprocess.run(
            [str(executable), "/PID", str(process_id), "/T", "/F"],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout_seconds,
            env=_safe_environment(),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


async def _settle_task(task: asyncio.Task[_TaskResult]) -> None:
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            continue
        except BaseException:
            break


@dataclass(frozen=True, slots=True)
class Wan22Backend:
    """Invoke one qualified external Wan2.2 TI2V runtime."""

    repository_root: Path
    checkpoint_dir: Path
    python_executable: Path
    output_root: Path
    checkpoint_manifest_sha256: str
    minimum_free_disk_bytes: int
    minimum_free_vram_bytes: int
    deadline_seconds: int = 7_200
    cancellation_poll_seconds: float = 0.5
    termination_grace_seconds: float = 10.0

    def __post_init__(self) -> None:
        repository = _resolve_existing_directory(self.repository_root, "Wan2.2 repository root")
        checkpoint = _resolve_existing_directory(self.checkpoint_dir, "checkpoint directory")
        python = _resolve_existing_file(self.python_executable, "Wan2.2 Python")
        output = _resolve_existing_directory(self.output_root, "Wan2.2 output root")
        generate = repository / "generate.py"
        if not generate.is_file() or _is_link_or_reparse_point(generate):
            raise Wan22ConfigurationError("Wan2.2 repository must contain a regular generate.py")
        if _current_repository_revision(repository) != WAN22_CODE_REVISION:
            raise Wan22ConfigurationError("Wan2.2 repository does not match the pinned revision")
        if len(self.checkpoint_manifest_sha256) != 64 or any(
            item not in "0123456789abcdef" for item in self.checkpoint_manifest_sha256
        ):
            raise Wan22ConfigurationError("checkpoint manifest pin must be lowercase SHA-256")
        if _checkpoint_manifest_sha256(checkpoint) != self.checkpoint_manifest_sha256:
            raise Wan22ConfigurationError("checkpoint files do not match the qualified manifest")
        if (
            min(self.minimum_free_disk_bytes, self.minimum_free_vram_bytes, self.deadline_seconds)
            <= 0
        ):
            raise Wan22ConfigurationError("qualified resource limits and deadline must be positive")
        if self.cancellation_poll_seconds <= 0 or self.termination_grace_seconds <= 0:
            raise Wan22ConfigurationError("process timing limits must be positive")
        object.__setattr__(self, "repository_root", repository)
        object.__setattr__(self, "checkpoint_dir", checkpoint)
        object.__setattr__(self, "python_executable", python)
        object.__setattr__(self, "output_root", output)

    @property
    def name(self) -> str:
        return "wan22-ti2v"

    @property
    def revision(self) -> str:
        return WAN22_BACKEND_REVISION

    def capabilities(self) -> tuple[ModelCapability, ...]:
        return (
            ModelCapability(
                model_id=WAN22_MODEL_ID,
                display_name="Wan2.2 TI2V 5B",
                modes=frozenset({GenerationMode.IMAGE_TO_VIDEO}),
                resolutions=WAN22_AREA_PRESETS,
                frame_counts=WAN22_FRAME_COUNTS,
            ),
        )

    def _supports(self, request: GenerationRequest) -> bool:
        manifest = request.image_conditioning
        return (
            request.model == WAN22_MODEL_ID
            and request.mode is GenerationMode.IMAGE_TO_VIDEO
            and request.resolution in WAN22_AREA_PRESETS
            and request.frame_count in WAN22_FRAME_COUNTS
            and manifest is not None
            and manifest.required_backend == self.name
            and manifest.required_backend_revision == self.revision
        )

    def _child_environment(self) -> dict[str, str]:
        environment = _safe_environment()
        path = environment.get("PATH")
        environment["PATH"] = str(self.python_executable.parent) + (
            os.pathsep + path if path else ""
        )
        return environment

    def _runtime_is_available(self) -> bool:
        try:
            return not (
                _resolve_existing_directory(self.repository_root, "Wan2.2 repository root")
                != self.repository_root
                or _resolve_existing_directory(self.checkpoint_dir, "checkpoint directory")
                != self.checkpoint_dir
                or _resolve_existing_file(self.python_executable, "Wan2.2 Python")
                != self.python_executable
                or _resolve_existing_directory(self.output_root, "Wan2.2 output root")
                != self.output_root
                or _current_repository_revision(self.repository_root) != WAN22_CODE_REVISION
            )
        except (OSError, Wan22ConfigurationError):
            return False

    def _preflight(self) -> bool:
        if shutil.disk_usage(self.output_root).free < self.minimum_free_disk_bytes:
            return False
        try:
            completed = subprocess.run(
                [str(self.python_executable), "-c", _CUDA_PROBE],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(self.repository_root),
                env=self._child_environment(),
            )
            payload: Any = json.loads(completed.stdout)
            return (
                bool(payload["cuda"]) and int(payload["free_vram"]) >= self.minimum_free_vram_bytes
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

    def _command(
        self,
        request: GenerationRequest,
        image_path: Path,
        output_path: Path,
        resolution: Resolution,
    ) -> tuple[str, ...]:
        return (
            str(self.python_executable),
            "-c",
            _PROMPT_RUNNER,
            "--task",
            WAN22_TASK,
            "--size",
            f"{request.width}*{request.height}",
            "--frame_num",
            str(request.frame_count),
            "--ckpt_dir",
            str(self.checkpoint_dir),
            "--save_file",
            str(output_path),
            "--base_seed",
            str(request.seed % (2**64)),
            "--offload_model",
            "True",
            "--convert_model_dtype",
            "--t5_cpu",
            "--image",
            str(image_path),
            "--video-app-expected-width",
            str(resolution.width),
            "--video-app-expected-height",
            str(resolution.height),
        )

    async def _spawn(self, command: tuple[str, ...]) -> asyncio.subprocess.Process:
        options: dict[str, Any] = {}
        if os.name == "nt":
            options["creationflags"] = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        else:
            options["start_new_session"] = True
        return await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            cwd=str(self.repository_root),
            env=self._child_environment(),
            **options,
        )

    async def _signal_tree(self, process: asyncio.subprocess.Process, *, force: bool) -> None:
        process_id = getattr(process, "pid", None)
        if os.name == "nt" and isinstance(process_id, int) and process_id > 0:
            if await asyncio.to_thread(
                _taskkill_windows_process_tree, process_id, self.termination_grace_seconds
            ):
                return
        elif isinstance(process_id, int) and process_id > 0:
            kill_group = cast(Callable[[int, int], None] | None, getattr(os, "killpg", None))
            if kill_group is not None:
                with suppress(OSError, ProcessLookupError):
                    kill_group(
                        process_id,
                        int(getattr(signal, "SIGKILL", 9)) if force else int(signal.SIGTERM),
                    )
                    return
        if process.returncode is None:
            with suppress(OSError, ProcessLookupError):
                (process.kill if force else process.terminate)()

    async def _stop(self, process: asyncio.subprocess.Process) -> None:
        if process.returncode is None:
            await self._signal_tree(process, force=False)
        try:
            await asyncio.wait_for(process.wait(), timeout=self.termination_grace_seconds)
        except asyncio.TimeoutError:
            await self._signal_tree(process, force=True)
            await asyncio.wait_for(process.wait(), timeout=self.termination_grace_seconds)

    async def generate(
        self, request: GenerationRequest, context: GenerationContext
    ) -> BackendOutput:
        if not self._supports(request) or context.resolve_input is None:
            raise BackendFailureError(ErrorCode.UNSUPPORTED_PARAMETERS, retryable=False)
        if await context.is_cancellation_requested():
            raise BackendCancelledError
        if not await asyncio.to_thread(self._runtime_is_available):
            raise BackendFailureError(ErrorCode.MODEL_UNAVAILABLE, retryable=False)
        if not await asyncio.to_thread(self._preflight):
            raise BackendFailureError(ErrorCode.INSUFFICIENT_RESOURCES, retryable=True)
        manifest = request.image_conditioning
        assert manifest is not None
        try:
            source_path = await context.resolve_input(manifest.source_storage_key)
        except (OSError, ValueError) as error:
            raise BackendFailureError(ErrorCode.GENERATION_FAILED, retryable=False) from error
        derivative_path = self.output_root / f"{uuid4().hex}.conditioning.png"
        output_path = self.output_root / f"{uuid4().hex}.mp4"
        evidence = await asyncio.to_thread(_prepare_input, source_path, request, derivative_path)
        resolution = _best_output_size(
            evidence.derivative_width,
            evidence.derivative_height,
            request.width * request.height,
        )
        command = self._command(request, derivative_path, output_path, resolution)
        spawn = asyncio.create_task(self._spawn(command))
        try:
            process = await asyncio.shield(spawn)
        except asyncio.CancelledError:
            await _settle_task(spawn)
            if not spawn.cancelled() and spawn.exception() is None:
                await self._stop(spawn.result())
            derivative_path.unlink(missing_ok=True)
            output_path.unlink(missing_ok=True)
            raise
        except OSError as error:
            derivative_path.unlink(missing_ok=True)
            raise BackendFailureError(ErrorCode.MODEL_UNAVAILABLE, retryable=False) from error
        communication = asyncio.create_task(process.communicate(request.prompt.encode("utf-8")))
        started = asyncio.get_running_loop().time()
        try:
            while not communication.done():
                if await context.is_cancellation_requested():
                    raise BackendCancelledError
                if asyncio.get_running_loop().time() - started > self.deadline_seconds:
                    raise BackendFailureError(ErrorCode.GENERATION_FAILED, retryable=True)
                try:
                    await asyncio.wait_for(
                        asyncio.shield(communication), timeout=self.cancellation_poll_seconds
                    )
                except asyncio.TimeoutError:
                    continue
            await communication
            if process.returncode != 0:
                raise BackendFailureError(ErrorCode.GENERATION_FAILED, retryable=True)
            _validate_mp4(output_path)
            return BackendOutput(
                temporary_path=output_path,
                resolution=resolution,
                frame_count=request.frame_count,
                duration_seconds=None,
                conditioning_evidence=evidence,
            )
        except BaseException:
            await self._stop(process)
            communication.cancel()
            await asyncio.gather(communication, return_exceptions=True)
            output_path.unlink(missing_ok=True)
            raise
        finally:
            derivative_path.unlink(missing_ok=True)
