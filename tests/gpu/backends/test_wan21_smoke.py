from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import math
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import cast
from unittest.mock import patch
from uuid import uuid4

import pytest

from video_app.backends.wan21.adapter import (
    WAN21_CODE_REVISION,
    WAN21_MODEL_REVISIONS,
    Wan21Backend,
)
from video_app.domain.models import (
    BackendOutput,
    GenerationMode,
    GenerationRequest,
    ModelCapability,
    Progress,
    Resolution,
)
from video_app.domain.ports import BackendCancelledError, GenerationContext

_APPLICATION_ROOT = Path(__file__).resolve().parents[3]
_RUN_GPU = os.environ.get("VIDEO_APP_RUN_WAN21_GPU_TESTS") == "1"
_PUBLIC_PROMPT = "A red paper boat drifting across a still pond"
_MODEL_ID = "wan21-t2v"
_RESOLUTION = Resolution(832, 480)
_FRAME_COUNT = 81
_SEED = 42
_EXTERNAL_RUNTIME_PROBE = r"""
import importlib.metadata
import json
import platform
import sys

import imageio
import imageio_ffmpeg
import torch

packages = []
for distribution in importlib.metadata.distributions():
    name = distribution.metadata.get('Name')
    if name:
        packages.append({'name': name, 'version': distribution.version})
packages.sort(key=lambda item: item['name'].casefold())

cuda_available = torch.cuda.is_available()
gpu = None
if cuda_available:
    device = torch.cuda.current_device()
    allocation = torch.empty((1,), device=device)
    torch.cuda.synchronize(device)
    del allocation
    torch.cuda.empty_cache()
    properties = torch.cuda.get_device_properties(device)
    free_memory, total_memory = torch.cuda.mem_get_info(device)
    major, minor = torch.cuda.get_device_capability(device)
    gpu = {
        'index': device,
        'name': properties.name,
        'compute_capability': f'{major}.{minor}',
        'total_memory_bytes': total_memory,
        'free_memory_bytes': free_memory,
    }

print(json.dumps({
    'python_version': platform.python_version(),
    'operating_system': platform.platform(),
    'torch_version': torch.__version__,
    'torch_cuda_version': torch.version.cuda,
    'cudnn_version': torch.backends.cudnn.version(),
    'imageio_version': imageio.__version__,
    'imageio_ffmpeg_version': imageio_ffmpeg.__version__,
    'ffmpeg_version': imageio_ffmpeg.get_ffmpeg_version(),
    'cuda_available': cuda_available,
    'gpu_count': torch.cuda.device_count(),
    'gpu': gpu,
    'packages': packages,
}, sort_keys=True))
"""
_VIDEO_PROBE = r"""
import imageio
import json
import sys

reader = imageio.get_reader(sys.argv[1])
frames = 0
width = None
height = None
try:
    for frame in reader:
        current_height, current_width = frame.shape[:2]
        if width is None:
            width = int(current_width)
            height = int(current_height)
        elif width != current_width or height != current_height:
            raise RuntimeError('inconsistent decoded dimensions')
        frames += 1
finally:
    reader.close()
print(json.dumps({'width': width, 'height': height, 'frame_count': frames}, sort_keys=True))
"""
_ENVIRONMENT_ALLOWLIST = frozenset(
    {
        "APPDATA",
        "COMSPEC",
        "CUDA_DEVICE_ORDER",
        "CUDA_HOME",
        "CUDA_PATH",
        "CUDA_VISIBLE_DEVICES",
        "HF_HOME",
        "HOME",
        "HUGGINGFACE_HUB_CACHE",
        "LD_LIBRARY_PATH",
        "LOCALAPPDATA",
        "NVIDIA_VISIBLE_DEVICES",
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "TMPDIR",
        "TORCH_HOME",
        "USERPROFILE",
        "WINDIR",
        "XDG_CACHE_HOME",
    }
)


@dataclass(frozen=True, slots=True)
class QualificationConfiguration:
    repository_root: Path
    checkpoint_dir: Path
    python_executable: Path
    report_directory: Path
    task: str
    model_revision: str
    generation_timeout_seconds: float
    cancellation_timeout_seconds: float
    gpu_observe_timeout_seconds: float


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _required_environment(name: str) -> str:
    value = os.environ.get(name)
    if value is None or not value.strip():
        raise AssertionError(f"{name} must be configured when GPU qualification is enabled")
    return value.strip()


def _positive_timeout(name: str, default: float) -> float:
    raw = os.environ.get(name, str(default))
    try:
        value = float(raw)
    except ValueError:
        raise AssertionError(f"{name} must be a number") from None
    if not math.isfinite(value) or value <= 0:
        raise AssertionError(f"{name} must be finite and positive")
    return value


def _is_link_or_reparse_point(path: Path) -> bool:
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return path.is_symlink() or bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _configuration() -> QualificationConfiguration:
    repository_root = Path(_required_environment("VIDEO_APP_WAN21_REPOSITORY_ROOT"))
    checkpoint_dir = Path(_required_environment("VIDEO_APP_WAN21_CHECKPOINT_DIR"))
    python_executable = Path(_required_environment("VIDEO_APP_WAN21_PYTHON"))
    report_directory = Path(_required_environment("VIDEO_APP_WAN21_QUALIFICATION_DIR"))
    for path, name, expected_type in (
        (repository_root, "VIDEO_APP_WAN21_REPOSITORY_ROOT", "directory"),
        (checkpoint_dir, "VIDEO_APP_WAN21_CHECKPOINT_DIR", "directory"),
        (python_executable, "VIDEO_APP_WAN21_PYTHON", "file"),
        (report_directory, "VIDEO_APP_WAN21_QUALIFICATION_DIR", "directory"),
    ):
        if not path.is_absolute():
            raise AssertionError(f"{name} must be absolute")
        exists_with_type = path.is_dir() if expected_type == "directory" else path.is_file()
        if not exists_with_type:
            raise AssertionError(f"{name} must be an existing {expected_type}")
        if _is_link_or_reparse_point(path):
            raise AssertionError(f"{name} must not be a link or reparse point")
    repository_root = repository_root.resolve(strict=True)
    checkpoint_dir = checkpoint_dir.resolve(strict=True)
    python_executable = python_executable.resolve(strict=True)
    report_directory = report_directory.resolve(strict=True)
    for path, name in (
        (repository_root, "VIDEO_APP_WAN21_REPOSITORY_ROOT"),
        (checkpoint_dir, "VIDEO_APP_WAN21_CHECKPOINT_DIR"),
        (python_executable, "VIDEO_APP_WAN21_PYTHON"),
    ):
        if path == _APPLICATION_ROOT or path.is_relative_to(_APPLICATION_ROOT):
            raise AssertionError(f"{name} must be outside the application repository")
    for protected_root in (_APPLICATION_ROOT, repository_root, checkpoint_dir):
        if report_directory == protected_root or report_directory.is_relative_to(protected_root):
            raise AssertionError(
                "VIDEO_APP_WAN21_QUALIFICATION_DIR must be outside source and checkpoint trees"
            )

    task = _required_environment("VIDEO_APP_WAN21_TASK")
    model_revision = _required_environment("VIDEO_APP_WAN21_MODEL_REVISION")
    if task not in WAN21_MODEL_REVISIONS:
        raise AssertionError("VIDEO_APP_WAN21_TASK is not supported by this adapter")
    if model_revision != WAN21_MODEL_REVISIONS[task]:
        raise AssertionError("VIDEO_APP_WAN21_MODEL_REVISION does not match the task pin")
    return QualificationConfiguration(
        repository_root=repository_root,
        checkpoint_dir=checkpoint_dir,
        python_executable=python_executable,
        report_directory=report_directory,
        task=task,
        model_revision=model_revision,
        generation_timeout_seconds=_positive_timeout(
            "VIDEO_APP_WAN21_GENERATION_TIMEOUT_SECONDS", 3600
        ),
        cancellation_timeout_seconds=_positive_timeout(
            "VIDEO_APP_WAN21_CANCELLATION_TIMEOUT_SECONDS", 120
        ),
        gpu_observe_timeout_seconds=_positive_timeout(
            "VIDEO_APP_WAN21_GPU_OBSERVE_TIMEOUT_SECONDS", 300
        ),
    )


def _probe_environment(python_executable: Path) -> dict[str, str]:
    environment = {
        name: value for name, value in os.environ.items() if name in _ENVIRONMENT_ALLOWLIST
    }
    python_directory = str(python_executable.parent)
    current_path = environment.get("PATH")
    environment["PATH"] = (
        f"{python_directory}{os.pathsep}{current_path}" if current_path else python_directory
    )
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


def _json_object(raw: str, operation: str) -> dict[str, object]:
    lines = [line for line in raw.splitlines() if line.strip()]
    if not lines:
        raise AssertionError(f"{operation} returned no structured result")
    try:
        decoded: object = json.loads(lines[-1])
    except json.JSONDecodeError:
        raise AssertionError(f"{operation} returned invalid structured data") from None
    if not isinstance(decoded, dict) or any(not isinstance(key, str) for key in decoded):
        raise AssertionError(f"{operation} returned an invalid object")
    return cast(dict[str, object], decoded)


def _run_external_json(
    python_executable: Path,
    script: str,
    *,
    arguments: tuple[str, ...] = (),
    timeout_seconds: float,
) -> dict[str, object]:
    try:
        completed = subprocess.run(
            [str(python_executable), "-I", "-c", script, *arguments],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=_probe_environment(python_executable),
        )
    except (OSError, subprocess.SubprocessError):
        raise AssertionError("external Wan2.1 runtime probe failed") from None
    return _json_object(completed.stdout, "external Wan2.1 runtime probe")


def _git_state(root: Path) -> dict[str, object]:
    environment = _probe_environment(Path(sys.executable).resolve(strict=True))
    discovered_git = shutil.which("git", path=environment.get("PATH"))
    if discovered_git is None:
        raise AssertionError("Git is required for qualification evidence")
    git_executable = Path(discovered_git).resolve(strict=True)
    try:
        revision = subprocess.run(
            [str(git_executable), "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
            env=environment,
        ).stdout.strip()
        status = subprocess.run(
            [
                str(git_executable),
                "-C",
                str(root),
                "status",
                "--porcelain",
                "--untracked-files=all",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
            env=environment,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        raise AssertionError("Git state could not be verified") from None
    if not revision:
        raise AssertionError("Git revision is empty")
    return {"revision": revision, "clean": not status}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _checkpoint_manifest(root: Path) -> dict[str, object]:
    started = time.monotonic()
    entries: list[tuple[str, int, str]] = []

    def fail_walk(_: OSError) -> None:
        raise AssertionError("checkpoint manifest could not read the complete directory") from None

    for current_root, directories, filenames in os.walk(
        root,
        followlinks=False,
        onerror=fail_walk,
    ):
        directories.sort()
        filenames.sort()
        current = Path(current_root)
        for directory in directories:
            path = current / directory
            if _is_link_or_reparse_point(path):
                raise AssertionError(
                    "checkpoint manifest does not accept linked or reparse-point directories"
                )
        for filename in filenames:
            path = current / filename
            if _is_link_or_reparse_point(path):
                raise AssertionError(
                    "checkpoint manifest does not accept linked or reparse-point files"
                )
            if not path.is_file():
                raise AssertionError("checkpoint manifest contains a non-file entry")
            relative = path.relative_to(root).as_posix()
            size = path.stat().st_size
            entries.append((relative, size, _sha256(path)))
    if not entries:
        raise AssertionError("checkpoint directory must not be empty")
    digest = hashlib.sha256()
    for relative, size, checksum in entries:
        digest.update(json.dumps([relative, size, checksum], separators=(",", ":")).encode("utf-8"))
        digest.update(b"\n")
    return {
        "file_count": len(entries),
        "total_bytes": sum(entry[1] for entry in entries),
        "content_manifest_sha256": digest.hexdigest(),
        "hash_duration_seconds": round(time.monotonic() - started, 3),
        "provenance": "operator_declared_revision_with_new_local_content_digest",
    }


def _nvidia_smi(environment: dict[str, str]) -> Path:
    candidates: list[Path] = []
    discovered = shutil.which("nvidia-smi", path=environment.get("PATH"))
    if discovered:
        candidates.append(Path(discovered))
    system_root = environment.get("SYSTEMROOT")
    if system_root:
        candidates.append(Path(system_root) / "System32" / "nvidia-smi.exe")
    candidates.append(Path("C:/Program Files/NVIDIA Corporation/NVSMI/nvidia-smi.exe"))
    for candidate in candidates:
        if candidate.is_absolute() and candidate.is_file():
            return candidate.resolve(strict=True)
    raise AssertionError("nvidia-smi is required for GPU qualification evidence")


def _nvidia_devices(executable: Path, environment: dict[str, str]) -> list[dict[str, object]]:
    try:
        completed = subprocess.run(
            [
                str(executable),
                "--query-gpu=index,name,driver_version,memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
            env=environment,
        )
    except (OSError, subprocess.SubprocessError):
        raise AssertionError("nvidia-smi GPU query failed") from None
    devices: list[dict[str, object]] = []
    for row in csv.reader(completed.stdout.splitlines()):
        if len(row) != 5:
            raise AssertionError("nvidia-smi returned an invalid GPU row")
        try:
            index = int(row[0].strip())
            total_memory_mib = int(row[3].strip())
            free_memory_mib = int(row[4].strip())
        except ValueError:
            raise AssertionError("nvidia-smi returned invalid memory data") from None
        name = row[1].strip()
        driver_version = row[2].strip()
        if not name or not driver_version:
            raise AssertionError("nvidia-smi returned incomplete GPU identity data")
        devices.append(
            {
                "index": index,
                "name": name,
                "driver_version": driver_version,
                "total_memory_mib": total_memory_mib,
                "free_memory_mib": free_memory_mib,
            }
        )
    if not devices:
        raise AssertionError("nvidia-smi reported no GPUs")
    return devices


def _nvidia_compute_pids(executable: Path, environment: dict[str, str]) -> set[int]:
    try:
        completed = subprocess.run(
            [
                str(executable),
                "--query-compute-apps=pid",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
            env=environment,
        )
    except (OSError, subprocess.SubprocessError):
        raise AssertionError("nvidia-smi compute-process query failed") from None
    process_ids: set[int] = set()
    for line in completed.stdout.splitlines():
        value = line.strip()
        if not value:
            continue
        if value.isdigit():
            process_ids.add(int(value))
            continue
        if value.casefold() == "no running processes found":
            continue
        raise AssertionError("nvidia-smi returned invalid compute-process data")
    return process_ids


def _mp4_structure(path: Path) -> dict[str, object]:
    file_size = path.stat().st_size
    if file_size < 8:
        raise AssertionError("generated MP4 is too small for a top-level box")

    position = 0
    box_count = 0
    first_box: bytes | None = None
    moov_payload_bytes = 0
    mdat_payload_bytes = 0
    with path.open("rb") as source:
        while position < file_size:
            remaining = file_size - position
            if remaining < 8:
                raise AssertionError("generated MP4 has a trailing partial box header")
            source.seek(position)
            header = source.read(8)
            if len(header) != 8:
                raise AssertionError("generated MP4 has a truncated box header")
            declared_size = int.from_bytes(header[:4], "big")
            box_type = header[4:8]
            header_size = 8
            if declared_size == 1:
                extended_size = source.read(8)
                if len(extended_size) != 8:
                    raise AssertionError("generated MP4 has a truncated extended box header")
                declared_size = int.from_bytes(extended_size, "big")
                header_size = 16
            elif declared_size == 0:
                declared_size = remaining
            if declared_size < header_size or declared_size > remaining:
                raise AssertionError("generated MP4 has an invalid top-level box size")

            payload_size = declared_size - header_size
            if first_box is None:
                first_box = box_type
            if box_type == b"moov":
                moov_payload_bytes += payload_size
            elif box_type == b"mdat":
                mdat_payload_bytes += payload_size
            box_count += 1
            position += declared_size

    if first_box != b"ftyp":
        raise AssertionError("generated MP4 does not start with ftyp")
    if moov_payload_bytes <= 0 or mdat_payload_bytes <= 0:
        raise AssertionError("generated MP4 lacks nonempty moov or mdat payloads")
    return {
        "first_box": "ftyp",
        "top_level_box_count": box_count,
        "moov_payload_bytes": moov_payload_bytes,
        "mdat_payload_bytes": mdat_payload_bytes,
    }


def _atomic_report(directory: Path, report: dict[str, object]) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    identifier = uuid4().hex
    final_path = directory / f"wan21-qualification-{stamp}-{identifier}.json"
    partial_path = directory / f".{identifier}.part"
    payload = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
    try:
        with partial_path.open("xb") as destination:
            destination.write(payload)
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(partial_path, final_path)
    except BaseException:
        partial_path.unlink(missing_ok=True)
        raise
    return final_path


def _capability() -> ModelCapability:
    return ModelCapability(
        model_id=_MODEL_ID,
        display_name="Wan2.1 Text to Video qualification",
        modes=frozenset({GenerationMode.TEXT_TO_VIDEO}),
        resolutions=frozenset({_RESOLUTION}),
        frame_counts=frozenset({_FRAME_COUNT}),
    )


def _request() -> GenerationRequest:
    return GenerationRequest(
        prompt=_PUBLIC_PROMPT,
        model=_MODEL_ID,
        resolution=_RESOLUTION,
        frame_count=_FRAME_COUNT,
        seed=_SEED,
    )


def _backend(configuration: QualificationConfiguration, output_root: Path) -> Wan21Backend:
    return Wan21Backend(
        repository_root=configuration.repository_root,
        checkpoint_dir=configuration.checkpoint_dir,
        python_executable=configuration.python_executable,
        output_root=output_root,
        task=configuration.task,
        model_revision=configuration.model_revision,
        model_capabilities=(_capability(),),
        cancellation_poll_seconds=1.0,
        termination_grace_seconds=10.0,
    )


async def _wait_for_gpu_processes(
    generation: asyncio.Task[BackendOutput],
    nvidia_smi: Path,
    environment: dict[str, str],
    timeout_seconds: float,
) -> set[int]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if generation.done():
            await generation
            raise AssertionError("cancellation generation ended before GPU observation")
        pids = await asyncio.to_thread(_nvidia_compute_pids, nvidia_smi, environment)
        if pids:
            return pids
        await asyncio.sleep(1)
    raise AssertionError("Wan2.1 process tree was not observed on the GPU before timeout")


async def _wait_for_gpu_processes_to_clear(
    nvidia_smi: Path,
    environment: dict[str, str],
    timeout_seconds: float,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        pids = await asyncio.to_thread(_nvidia_compute_pids, nvidia_smi, environment)
        if not pids:
            return
        await asyncio.sleep(1)
    raise AssertionError("GPU compute processes remained after Wan2.1 cleanup")


async def _force_settle_generation(
    backend: Wan21Backend,
    generation: asyncio.Task[BackendOutput],
    process: asyncio.subprocess.Process | None,
    timeout_seconds: float,
) -> None:
    generation.cancel()
    done, _ = await asyncio.wait({generation}, timeout=timeout_seconds)
    if not done and process is not None and process.returncode is None:
        await backend._signal_process_tree(process, force=True)
        try:
            await asyncio.wait_for(process.wait(), timeout=min(timeout_seconds, 30.0))
        except asyncio.TimeoutError:
            raise AssertionError("Wan2.1 process did not stop after forced cleanup") from None
        generation.cancel()
        done, _ = await asyncio.wait(
            {generation},
            timeout=min(timeout_seconds, 30.0),
        )
    if not done:
        raise AssertionError("Wan2.1 generation task did not settle after forced cleanup")
    if not generation.cancelled():
        generation.exception()


async def _generate_and_measure(
    configuration: QualificationConfiguration,
    output_root: Path,
    nvidia_smi: Path,
    environment: dict[str, str],
) -> dict[str, object]:
    progress: list[Progress] = []
    observed_processes: list[asyncio.subprocess.Process] = []
    backend = _backend(configuration, output_root)
    original_spawn = Wan21Backend._spawn_process

    async def observed_spawn(
        current_backend: Wan21Backend,
        request: GenerationRequest,
        output_path: Path,
    ) -> asyncio.subprocess.Process:
        process = await original_spawn(current_backend, request, output_path)
        observed_processes.append(process)
        return process

    async def report_progress(item: Progress) -> None:
        progress.append(item)

    async def not_cancelled() -> bool:
        return False

    started = time.monotonic()
    with patch.object(Wan21Backend, "_spawn_process", new=observed_spawn):
        generation = asyncio.create_task(
            backend.generate(
                _request(),
                GenerationContext(
                    "gpu-qualification-generation",
                    report_progress,
                    not_cancelled,
                ),
            )
        )
        done, _ = await asyncio.wait(
            {generation},
            timeout=configuration.generation_timeout_seconds,
        )
        if not done:
            process = observed_processes[0] if observed_processes else None
            await _force_settle_generation(
                backend,
                generation,
                process,
                configuration.cancellation_timeout_seconds,
            )
            raise AssertionError("Wan2.1 generation exceeded its timeout")
        output = generation.result()
    duration = time.monotonic() - started
    try:
        await _wait_for_gpu_processes_to_clear(
            nvidia_smi,
            environment,
            configuration.gpu_observe_timeout_seconds,
        )
        independent = await asyncio.to_thread(
            _run_external_json,
            configuration.python_executable,
            _VIDEO_PROBE,
            arguments=(str(output.temporary_path),),
            timeout_seconds=300,
        )
        if independent.get("width") != _RESOLUTION.width:
            raise AssertionError("independent video probe reported the wrong width")
        if independent.get("height") != _RESOLUTION.height:
            raise AssertionError("independent video probe reported the wrong height")
        if independent.get("frame_count") != _FRAME_COUNT:
            raise AssertionError("independent video probe reported the wrong frame count")
        structure = await asyncio.to_thread(_mp4_structure, output.temporary_path)
        return {
            "duration_seconds": round(duration, 3),
            "seed": _SEED,
            "width": _RESOLUTION.width,
            "height": _RESOLUTION.height,
            "frame_count": _FRAME_COUNT,
            "size_bytes": output.temporary_path.stat().st_size,
            "sha256": await asyncio.to_thread(_sha256, output.temporary_path),
            "independent_decode": independent,
            "structural_validation": structure,
            "progress_reports": len(progress),
            "compute_process_count_after": 0,
            "nvidia_after_generation": await asyncio.to_thread(
                _nvidia_devices, nvidia_smi, environment
            ),
        }
    finally:
        output.temporary_path.unlink(missing_ok=True)


async def _cancel_and_measure(
    configuration: QualificationConfiguration,
    output_root: Path,
    nvidia_smi: Path,
    environment: dict[str, str],
) -> dict[str, object]:
    cancel = asyncio.Event()
    spawned = asyncio.Event()
    observed_processes: list[asyncio.subprocess.Process] = []
    backend = _backend(configuration, output_root)
    original_spawn = Wan21Backend._spawn_process

    async def observed_spawn(
        backend: Wan21Backend,
        request: GenerationRequest,
        output_path: Path,
    ) -> asyncio.subprocess.Process:
        process = await original_spawn(backend, request, output_path)
        observed_processes.append(process)
        spawned.set()
        return process

    async def report_progress(_: Progress) -> None:
        return None

    async def is_cancelled() -> bool:
        return cancel.is_set()

    with patch.object(Wan21Backend, "_spawn_process", new=observed_spawn):
        generation = asyncio.create_task(
            backend.generate(
                _request(),
                GenerationContext(
                    "gpu-qualification-cancellation",
                    report_progress,
                    is_cancelled,
                ),
            )
        )
        try:
            await asyncio.wait_for(
                spawned.wait(),
                timeout=configuration.gpu_observe_timeout_seconds,
            )
            if not observed_processes:
                raise AssertionError("Wan2.1 process was not captured")
            process = observed_processes[0]
            observed_gpu_pids = await _wait_for_gpu_processes(
                generation,
                nvidia_smi,
                environment,
                configuration.gpu_observe_timeout_seconds,
            )
            if process.pid not in observed_gpu_pids:
                raise AssertionError(
                    "captured Wan2.1 parent process was not visible in the GPU process list"
                )
            gpu_during_cancellation = await asyncio.to_thread(
                _nvidia_devices, nvidia_smi, environment
            )
            cancellation_started = time.monotonic()
            cancel.set()
            done, _ = await asyncio.wait(
                {generation},
                timeout=configuration.cancellation_timeout_seconds,
            )
            if not done:
                await _force_settle_generation(
                    backend,
                    generation,
                    process,
                    configuration.cancellation_timeout_seconds,
                )
                raise AssertionError("Wan2.1 cancellation cleanup exceeded its timeout")
            try:
                generation.result()
            except BackendCancelledError:
                pass
            else:
                raise AssertionError("Wan2.1 cancellation did not raise BackendCancelledError")
            cleanup_duration = time.monotonic() - cancellation_started
            if process.returncode is None:
                raise AssertionError("Wan2.1 parent process is still running after cancellation")
            await _wait_for_gpu_processes_to_clear(
                nvidia_smi,
                environment,
                configuration.gpu_observe_timeout_seconds,
            )
            if any(output_root.iterdir()):
                raise AssertionError("Wan2.1 cancellation left temporary candidates")
            return {
                "gpu_observed_before_cancel": True,
                "observed_compute_process_ids": sorted(observed_gpu_pids),
                "parent_was_compute_process": process.pid in observed_gpu_pids,
                "parent_pid": process.pid,
                "parent_returncode": process.returncode,
                "cleanup_duration_seconds": round(cleanup_duration, 3),
                "temporary_output_empty": True,
                "all_compute_processes_absent": True,
                "nvidia_during_cancellation": gpu_during_cancellation,
                "nvidia_after_cancellation": await asyncio.to_thread(
                    _nvidia_devices, nvidia_smi, environment
                ),
            }
        finally:
            cancel.set()
            if not generation.done():
                cleanup_process = observed_processes[0] if observed_processes else None
                await _force_settle_generation(
                    backend,
                    generation,
                    cleanup_process,
                    configuration.cancellation_timeout_seconds,
                )


class Wan21QualificationHarnessUnitTests(unittest.TestCase):
    def test_configuration_fails_closed_when_opted_in_without_runtime_paths(self) -> None:
        with (
            patch.dict(
                os.environ,
                {"VIDEO_APP_RUN_WAN21_GPU_TESTS": "1"},
                clear=True,
            ),
            self.assertRaisesRegex(
                AssertionError,
                "VIDEO_APP_WAN21_REPOSITORY_ROOT must be configured",
            ),
        ):
            _configuration()

    def test_timeout_configuration_rejects_non_finite_or_nonpositive_values(self) -> None:
        name = "VIDEO_APP_WAN21_GENERATION_TIMEOUT_SECONDS"
        for raw in ("nan", "inf", "-inf", "0", "-1"):
            with (
                self.subTest(raw=raw),
                patch.dict(os.environ, {name: raw}, clear=False),
                self.assertRaisesRegex(AssertionError, "finite and positive"),
            ):
                _positive_timeout(name, 1)

    def test_mp4_structure_records_required_top_level_boxes(self) -> None:
        def box(kind: bytes, payload: bytes) -> bytes:
            return (len(payload) + 8).to_bytes(4, "big") + kind + payload

        payload = box(b"ftyp", b"isom") + box(b"moov", b"metadata") + box(b"mdat", b"video-payload")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidate.mp4"
            path.write_bytes(payload)
            evidence = _mp4_structure(path)
            self.assertEqual(evidence["first_box"], "ftyp")
            self.assertEqual(evidence["top_level_box_count"], 3)
            self.assertEqual(evidence["moov_payload_bytes"], len(b"metadata"))
            self.assertEqual(evidence["mdat_payload_bytes"], len(b"video-payload"))

            path.write_bytes(payload[:-1])
            with self.assertRaisesRegex(AssertionError, "invalid top-level box size"):
                _mp4_structure(path)

    def test_checkpoint_manifest_is_stable_for_materialized_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "weights.bin").write_bytes(b"weights")
            nested = root / "config"
            nested.mkdir()
            (nested / "model.json").write_bytes(b"{}\n")

            first = _checkpoint_manifest(root)
            second = _checkpoint_manifest(root)
            self.assertEqual(first["file_count"], 2)
            self.assertEqual(first["total_bytes"], 10)
            self.assertEqual(
                first["content_manifest_sha256"],
                second["content_manifest_sha256"],
            )

    def test_nvidia_process_query_fails_on_command_or_parse_error(self) -> None:
        executable = Path("C:/NVIDIA/nvidia-smi.exe")
        with (
            patch.object(
                subprocess,
                "run",
                side_effect=subprocess.CalledProcessError(1, "nvidia-smi"),
            ),
            self.assertRaisesRegex(AssertionError, "compute-process query failed"),
        ):
            _nvidia_compute_pids(executable, {})

        malformed = subprocess.CompletedProcess(
            args=("nvidia-smi",),
            returncode=0,
            stdout="unstructured output\n",
            stderr="",
        )
        with (
            patch.object(subprocess, "run", return_value=malformed),
            self.assertRaisesRegex(AssertionError, "invalid compute-process data"),
        ):
            _nvidia_compute_pids(executable, {})

    def test_report_is_written_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = _atomic_report(root, {"schema_version": "test", "status": "passed"})
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")),
                {"schema_version": "test", "status": "passed"},
            )
            self.assertEqual(list(root.glob("*.part")), [])


@pytest.mark.gpu
@pytest.mark.integration
@unittest.skipUnless(
    _RUN_GPU,
    "set VIDEO_APP_RUN_WAN21_GPU_TESTS=1 to run the explicit GPU qualification",
)
class Wan21GpuQualificationTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_runtime_generation_and_cancellation_qualification(self) -> None:
        configuration = _configuration()
        report: dict[str, object] = {
            "schema_version": "wan21-gpu-qualification-v1",
            "status": "running",
            "phase": "configuration",
            "started_at": _utc_now(),
            "scope": {
                "task": configuration.task,
                "model_revision": configuration.model_revision,
                "width": _RESOLUTION.width,
                "height": _RESOLUTION.height,
                "frame_count": _FRAME_COUNT,
                "seed": _SEED,
                "production_model_selected": False,
            },
        }
        report_path: Path | None = None
        try:
            disk = shutil.disk_usage(configuration.report_directory)
            report["disk"] = {
                "total_bytes": disk.total,
                "free_bytes_before": disk.free,
            }
            report["phase"] = "source_state"
            application_state = await asyncio.to_thread(_git_state, _APPLICATION_ROOT)
            if application_state.get("clean") is not True:
                raise AssertionError("application repository must be clean for qualification")
            wan_state = await asyncio.to_thread(_git_state, configuration.repository_root)
            if wan_state.get("clean") is not True:
                raise AssertionError("Wan2.1 repository must be clean for qualification")
            if wan_state.get("revision") != WAN21_CODE_REVISION:
                raise AssertionError("Wan2.1 repository revision does not match the pin")
            report["application"] = application_state
            report["wan21"] = {
                **wan_state,
                "expected_revision": WAN21_CODE_REVISION,
            }

            report["phase"] = "checkpoint_manifest"
            report["checkpoint"] = await asyncio.to_thread(
                _checkpoint_manifest, configuration.checkpoint_dir
            )

            report["phase"] = "runtime_probe"
            runtime = await asyncio.to_thread(
                _run_external_json,
                configuration.python_executable,
                _EXTERNAL_RUNTIME_PROBE,
                timeout_seconds=120,
            )
            if runtime.get("cuda_available") is not True:
                raise AssertionError("external Wan2.1 Python does not have CUDA available")
            gpu_count = runtime.get("gpu_count")
            if not isinstance(gpu_count, int) or isinstance(gpu_count, bool) or gpu_count <= 0:
                raise AssertionError("external Wan2.1 Python reported no CUDA devices")
            packages = runtime.get("packages")
            if not isinstance(packages, list):
                raise AssertionError("external Wan2.1 Python returned no package inventory")
            package_inventory = json.dumps(
                packages,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            report["runtime"] = runtime
            report["installed_package_inventory_sha256"] = hashlib.sha256(
                package_inventory
            ).hexdigest()

            probe_environment = _probe_environment(configuration.python_executable)
            nvidia_smi = _nvidia_smi(probe_environment)
            await _wait_for_gpu_processes_to_clear(
                nvidia_smi,
                probe_environment,
                configuration.gpu_observe_timeout_seconds,
            )
            nvidia_before = await asyncio.to_thread(_nvidia_devices, nvidia_smi, probe_environment)
            report["nvidia_before"] = nvidia_before
            baseline_compute_pids = await asyncio.to_thread(
                _nvidia_compute_pids,
                nvidia_smi,
                probe_environment,
            )
            if baseline_compute_pids:
                raise AssertionError(
                    "GPU qualification requires an exclusive GPU with no compute processes"
                )
            report["compute_process_count_before"] = 0
            report["cuda_visible_devices_configured"] = bool(os.environ.get("CUDA_VISIBLE_DEVICES"))

            with tempfile.TemporaryDirectory(
                dir=configuration.report_directory,
                prefix="wan21-qualification-",
            ) as directory:
                output_root = Path(directory).resolve(strict=True)
                report["phase"] = "generation"
                report["generation"] = await _generate_and_measure(
                    configuration,
                    output_root,
                    nvidia_smi,
                    probe_environment,
                )
                report["phase"] = "cancellation"
                report["cancellation"] = await _cancel_and_measure(
                    configuration,
                    output_root,
                    nvidia_smi,
                    probe_environment,
                )

            report["phase"] = "complete"
            report["status"] = "passed"
        except BaseException as error:
            report["status"] = "failed"
            report["failure"] = {
                "phase": report.get("phase", "unknown"),
                "type": type(error).__name__,
            }
            raise
        finally:
            report["ended_at"] = _utc_now()
            current_disk = shutil.disk_usage(configuration.report_directory)
            disk_evidence = report.get("disk")
            if isinstance(disk_evidence, dict):
                cast(dict[str, object], disk_evidence)["free_bytes_after"] = current_disk.free
            report_path = _atomic_report(configuration.report_directory, report)
            print(f"Wan2.1 qualification evidence: {report_path.name}")

        self.assertIsNotNone(report_path)


if __name__ == "__main__":
    unittest.main()
