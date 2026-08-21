"""Cancellable subprocess adapter for a pinned external Wan2.1 checkout."""

from __future__ import annotations

import asyncio
import os
import signal
import stat
import struct
import subprocess
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import TypeVar, cast
from uuid import uuid4

from video_app.domain.models import (
    BackendOutput,
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

WAN21_CODE_REVISION = "9737cba9c1c3c4d04b33fcad41c111989865d315"
WAN21_MODEL_REVISIONS: Mapping[str, str] = MappingProxyType(
    {
        "t2v-1.3B": "37ec512624d61f7aa208f7ea8140a131f93afc9a",
        "t2v-14B": "a064a6c71f5be440641209c07bf2a5ce7a2ff5e4",
    }
)

_SUPPORTED_RESOLUTIONS: Mapping[str, frozenset[Resolution]] = MappingProxyType(
    {
        "t2v-1.3B": frozenset({Resolution(832, 480), Resolution(480, 832)}),
        "t2v-14B": frozenset(
            {
                Resolution(832, 480),
                Resolution(480, 832),
                Resolution(1280, 720),
                Resolution(720, 1280),
            }
        ),
    }
)
_SUPPORTED_FRAME_COUNTS = frozenset({81})
_PROMPT_RUNNER = """\
import imageio
import runpy
import sys

arguments = sys.argv[1:]

def value(name):
    return arguments[arguments.index(name) + 1]

output_path = value('--save_file')
expected_width, expected_height = (int(item) for item in value('--size').split('*'))
expected_frames = int(value('--frame_num'))
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
        "MKL_NUM_THREADS",
        "NVIDIA_VISIBLE_DEVICES",
        "OMP_NUM_THREADS",
        "PATH",
        "PATHEXT",
        "PYTORCH_ALLOC_CONF",
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


class Wan21ConfigurationError(ValueError):
    """Raised when the external Wan2.1 runtime is not the pinned runtime."""


def _is_link_or_reparse_point(path: Path) -> bool:
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return path.is_symlink() or bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _resolve_existing_directory(path: Path, field: str) -> Path:
    if not path.is_absolute():
        raise Wan21ConfigurationError(f"{field} must be absolute")
    if not path.exists() or not path.is_dir():
        raise Wan21ConfigurationError(f"{field} must be an existing directory")
    if _is_link_or_reparse_point(path):
        raise Wan21ConfigurationError(f"{field} must not be a link or reparse point")
    return path.resolve(strict=True)


def _resolve_existing_file(path: Path, field: str) -> Path:
    if not path.is_absolute():
        raise Wan21ConfigurationError(f"{field} must be absolute")
    if not path.exists() or not path.is_file():
        raise Wan21ConfigurationError(f"{field} must be an existing file")
    if _is_link_or_reparse_point(path):
        raise Wan21ConfigurationError(f"{field} must not be a link or reparse point")
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
        revision_check = subprocess.run(
            ["git", "-C", str(repository_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
            env=_safe_environment(),
        )
        source_check = subprocess.run(
            [
                "git",
                "-C",
                str(repository_root),
                "status",
                "--porcelain",
                "--untracked-files=all",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
            env=_safe_environment(),
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise Wan21ConfigurationError("Wan2.1 repository revision could not be verified") from error
    if source_check.stdout.strip():
        raise Wan21ConfigurationError("Wan2.1 generation sources contain local changes")
    revision = revision_check.stdout.strip()
    if not revision:
        raise Wan21ConfigurationError("Wan2.1 repository revision could not be verified")
    return revision


def _mp4_box_payload_sizes(path: Path) -> tuple[tuple[bytes, int], ...]:
    file_size = path.stat().st_size
    boxes: list[tuple[bytes, int]] = []
    offset = 0
    with path.open("rb") as generated:
        while offset < file_size:
            generated.seek(offset)
            header = generated.read(8)
            if len(header) != 8:
                raise BackendFailureError(ErrorCode.GENERATION_FAILED, retryable=True)
            box_size, kind = struct.unpack(">I4s", header)
            header_size = 8
            if box_size == 1:
                extended_size = generated.read(8)
                if len(extended_size) != 8:
                    raise BackendFailureError(ErrorCode.GENERATION_FAILED, retryable=True)
                box_size = struct.unpack(">Q", extended_size)[0]
                header_size = 16
            elif box_size == 0:
                box_size = file_size - offset
            if box_size < header_size or offset + box_size > file_size:
                raise BackendFailureError(ErrorCode.GENERATION_FAILED, retryable=True)
            boxes.append((kind, box_size - header_size))
            offset += box_size
    return tuple(boxes)


def _validate_mp4(path: Path) -> None:
    if not path.is_absolute() or not path.exists() or not path.is_file():
        raise BackendFailureError(ErrorCode.GENERATION_FAILED, retryable=True)
    if _is_link_or_reparse_point(path):
        raise BackendFailureError(ErrorCode.GENERATION_FAILED, retryable=True)
    if path.suffix.lower() != ".mp4" or path.stat().st_size <= 24:
        raise BackendFailureError(ErrorCode.GENERATION_FAILED, retryable=True)
    boxes = _mp4_box_payload_sizes(path)
    if not boxes or boxes[0][0] != b"ftyp":
        raise BackendFailureError(ErrorCode.GENERATION_FAILED, retryable=True)
    payload_sizes = {kind: size for kind, size in boxes}
    if payload_sizes.get(b"moov", 0) <= 0 or payload_sizes.get(b"mdat", 0) <= 0:
        raise BackendFailureError(ErrorCode.GENERATION_FAILED, retryable=True)


def _remove_if_present(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return


def _taskkill_windows_process_tree(process_id: int, timeout_seconds: float) -> bool:
    system_root = os.environ.get("SYSTEMROOT")
    if not system_root:
        return False
    executable = Path(system_root) / "System32" / "taskkill.exe"
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


async def _finish_cleanup(cleanup: asyncio.Task[None]) -> None:
    deferred_cancellation: asyncio.CancelledError | None = None
    while not cleanup.done():
        try:
            await asyncio.shield(cleanup)
        except asyncio.CancelledError as error:
            deferred_cancellation = error
        except BaseException:
            break
    await cleanup
    if deferred_cancellation is not None:
        raise deferred_cancellation


async def _settle_task(task: asyncio.Task[_TaskResult]) -> None:
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            continue
        except BaseException:
            break


@dataclass(frozen=True, slots=True)
class Wan21Backend:
    """Invoke a locally installed, revision-pinned Wan2.1 runtime."""

    repository_root: Path
    checkpoint_dir: Path
    python_executable: Path
    output_root: Path
    task: str
    model_revision: str
    model_capabilities: tuple[ModelCapability, ...]
    cancellation_poll_seconds: float = 0.5
    termination_grace_seconds: float = 10.0

    def __post_init__(self) -> None:
        repository_root = _resolve_existing_directory(
            self.repository_root, "Wan2.1 repository root"
        )
        checkpoint_dir = _resolve_existing_directory(self.checkpoint_dir, "checkpoint directory")
        python_executable = _resolve_existing_file(self.python_executable, "Wan2.1 Python")
        output_root = _resolve_existing_directory(self.output_root, "Wan2.1 output root")
        generate_script = repository_root / "generate.py"
        if not generate_script.is_file() or _is_link_or_reparse_point(generate_script):
            raise Wan21ConfigurationError("Wan2.1 repository must contain a regular generate.py")
        if self.task not in WAN21_MODEL_REVISIONS:
            raise Wan21ConfigurationError("unsupported Wan2.1 task")
        if self.model_revision != WAN21_MODEL_REVISIONS[self.task]:
            raise Wan21ConfigurationError("Wan2.1 model revision does not match the pinned task")
        if _current_repository_revision(repository_root) != WAN21_CODE_REVISION:
            raise Wan21ConfigurationError("Wan2.1 repository does not match the pinned revision")
        if not self.model_capabilities:
            raise Wan21ConfigurationError("Wan2.1 backend requires at least one model capability")
        supported_resolutions = _SUPPORTED_RESOLUTIONS[self.task]
        for capability in self.model_capabilities:
            if capability.modes != frozenset({GenerationMode.TEXT_TO_VIDEO}):
                raise Wan21ConfigurationError("Wan2.1 MVP supports only text-to-video")
            if not capability.resolutions.issubset(supported_resolutions):
                raise Wan21ConfigurationError("model capability contains an unsupported resolution")
            if not capability.frame_counts.issubset(_SUPPORTED_FRAME_COUNTS):
                raise Wan21ConfigurationError(
                    "model capability contains an unsupported frame count"
                )
        if self.cancellation_poll_seconds <= 0:
            raise Wan21ConfigurationError("cancellation_poll_seconds must be positive")
        if self.termination_grace_seconds <= 0:
            raise Wan21ConfigurationError("termination_grace_seconds must be positive")
        object.__setattr__(self, "repository_root", repository_root)
        object.__setattr__(self, "checkpoint_dir", checkpoint_dir)
        object.__setattr__(self, "python_executable", python_executable)
        object.__setattr__(self, "output_root", output_root)

    @property
    def name(self) -> str:
        return "wan21"

    @property
    def revision(self) -> str:
        return f"wan2.1@{WAN21_CODE_REVISION};task={self.task};model@{self.model_revision}"

    def capabilities(self) -> tuple[ModelCapability, ...]:
        return self.model_capabilities

    def _supports(self, request: GenerationRequest) -> bool:
        return any(
            capability.enabled
            and request.model == capability.model_id
            and request.mode in capability.modes
            and request.resolution in capability.resolutions
            and request.frame_count in capability.frame_counts
            for capability in self.model_capabilities
        )

    def _command(self, request: GenerationRequest, output_path: Path) -> tuple[str, ...]:
        return (
            str(self.python_executable),
            "-c",
            _PROMPT_RUNNER,
            "--task",
            self.task,
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
        )

    def _runtime_is_available(self) -> bool:
        try:
            repository_root = _resolve_existing_directory(
                self.repository_root, "Wan2.1 repository root"
            )
            checkpoint_dir = _resolve_existing_directory(
                self.checkpoint_dir, "checkpoint directory"
            )
            python_executable = _resolve_existing_file(self.python_executable, "Wan2.1 Python")
            output_root = _resolve_existing_directory(self.output_root, "Wan2.1 output root")
            generate_script = repository_root / "generate.py"
            return (
                repository_root == self.repository_root
                and checkpoint_dir == self.checkpoint_dir
                and python_executable == self.python_executable
                and output_root == self.output_root
                and generate_script.is_file()
                and not _is_link_or_reparse_point(generate_script)
                and _current_repository_revision(repository_root) == WAN21_CODE_REVISION
            )
        except (OSError, Wan21ConfigurationError):
            return False

    def _child_environment(self) -> dict[str, str]:
        environment = _safe_environment()
        python_directory = str(self.python_executable.parent)
        current_path = environment.get("PATH")
        environment["PATH"] = (
            f"{python_directory}{os.pathsep}{current_path}" if current_path else python_directory
        )
        return environment

    async def _spawn_process(
        self,
        request: GenerationRequest,
        output_path: Path,
    ) -> asyncio.subprocess.Process:
        command = self._command(request, output_path)
        environment = self._child_environment()
        if os.name == "nt":
            return await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                cwd=str(self.repository_root),
                env=environment,
                creationflags=int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)),
            )
        return await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            cwd=str(self.repository_root),
            env=environment,
            start_new_session=True,
        )

    async def _signal_process_tree(
        self,
        process: asyncio.subprocess.Process,
        *,
        force: bool,
    ) -> None:
        process_id = getattr(process, "pid", None)
        if os.name == "nt" and isinstance(process_id, int) and process_id > 0:
            killed = await asyncio.to_thread(
                _taskkill_windows_process_tree,
                process_id,
                self.termination_grace_seconds,
            )
            if killed:
                return
        elif isinstance(process_id, int) and process_id > 0:
            kill_group = cast(
                Callable[[int, int], None] | None,
                getattr(os, "killpg", None),
            )
            if kill_group is not None:
                selected_signal = (
                    int(getattr(signal, "SIGKILL", 9)) if force else int(signal.SIGTERM)
                )
                try:
                    kill_group(process_id, selected_signal)
                    return
                except (OSError, ProcessLookupError):
                    pass
        if process.returncode is None:
            operation = process.kill if force else process.terminate
            with suppress(OSError, ProcessLookupError):
                operation()

    async def _stop_process(
        self,
        process: asyncio.subprocess.Process,
        communication: asyncio.Task[tuple[bytes, bytes]],
    ) -> None:
        if process.returncode is None:
            await self._signal_process_tree(process, force=False)
        try:
            await asyncio.wait_for(
                process.wait(),
                timeout=self.termination_grace_seconds,
            )
        except TimeoutError:
            if process.returncode is None:
                await self._signal_process_tree(process, force=True)
            try:
                await asyncio.wait_for(
                    process.wait(),
                    timeout=self.termination_grace_seconds,
                )
            except TimeoutError as error:
                communication.cancel()
                await asyncio.gather(communication, return_exceptions=True)
                raise BackendFailureError(
                    ErrorCode.GENERATION_FAILED,
                    retryable=True,
                ) from error
        try:
            await asyncio.wait_for(
                asyncio.shield(communication),
                timeout=self.termination_grace_seconds,
            )
        except TimeoutError:
            communication.cancel()
            await asyncio.gather(communication, return_exceptions=True)
        except Exception:
            await asyncio.gather(communication, return_exceptions=True)

    async def _clean_failed_run(
        self,
        process: asyncio.subprocess.Process,
        communication: asyncio.Task[tuple[bytes, bytes]],
        output_path: Path,
    ) -> None:
        try:
            await self._stop_process(process, communication)
        finally:
            await asyncio.to_thread(_remove_if_present, output_path)

    async def generate(
        self,
        request: GenerationRequest,
        context: GenerationContext,
    ) -> BackendOutput:
        if not self._supports(request):
            raise BackendFailureError(ErrorCode.UNSUPPORTED_PARAMETERS, retryable=False)
        if await context.is_cancellation_requested():
            raise BackendCancelledError
        if not await asyncio.to_thread(self._runtime_is_available):
            raise BackendFailureError(ErrorCode.MODEL_UNAVAILABLE, retryable=False)
        if await context.is_cancellation_requested():
            raise BackendCancelledError

        output_path = self.output_root / f"{uuid4().hex}.mp4"
        if output_path.parent != self.output_root:
            raise BackendFailureError(ErrorCode.GENERATION_FAILED, retryable=False)
        spawn = asyncio.create_task(self._spawn_process(request, output_path))
        try:
            process = await asyncio.shield(spawn)
        except asyncio.CancelledError as cancellation:
            await _settle_task(spawn)
            if spawn.cancelled():
                raise cancellation
            spawn_error = spawn.exception()
            if spawn_error is not None:
                raise cancellation from spawn_error
            process = spawn.result()
            cancel_communication = asyncio.create_task(process.communicate(b""))
            cleanup = asyncio.create_task(
                self._clean_failed_run(process, cancel_communication, output_path)
            )
            await _finish_cleanup(cleanup)
            raise cancellation
        except OSError as error:
            raise BackendFailureError(ErrorCode.MODEL_UNAVAILABLE, retryable=False) from error

        communication: asyncio.Task[tuple[bytes, bytes]] | None = None
        try:
            if await context.is_cancellation_requested():
                raise BackendCancelledError
            communication = asyncio.create_task(process.communicate(request.prompt.encode("utf-8")))
            while not communication.done():
                if await context.is_cancellation_requested():
                    raise BackendCancelledError
                try:
                    await asyncio.wait_for(
                        asyncio.shield(communication),
                        timeout=self.cancellation_poll_seconds,
                    )
                except TimeoutError:
                    continue
            await communication
            if await context.is_cancellation_requested():
                raise BackendCancelledError
            if process.returncode != 0:
                raise BackendFailureError(ErrorCode.GENERATION_FAILED, retryable=True)
            _validate_mp4(output_path)
            return BackendOutput(
                temporary_path=output_path,
                resolution=request.resolution,
                frame_count=request.frame_count,
                duration_seconds=None,
            )
        except BaseException:
            if communication is None:
                communication = asyncio.create_task(process.communicate(b""))
            cleanup = asyncio.create_task(
                self._clean_failed_run(process, communication, output_path)
            )
            await _finish_cleanup(cleanup)
            raise
