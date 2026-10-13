"""Typed runtime settings and standard infrastructure primitives."""

from __future__ import annotations

import json
import os
import re
import secrets
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from video_app.domain.models import GenerationMode, ModelCapability, Resolution
from video_app.infrastructure.database import DatabaseSettings


def _required(values: Mapping[str, str], name: str) -> str:
    value = values.get(name)
    if value is None or not value.strip():
        raise RuntimeError(f"{name} must be configured")
    return value.strip()


def _positive_int(values: Mapping[str, str], name: str, default: int) -> int:
    raw = values.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as error:
        raise RuntimeError(f"{name} must be an integer") from error
    if value <= 0:
        raise RuntimeError(f"{name} must be positive")
    return value


def _boolean(values: Mapping[str, str], name: str, default: bool = False) -> bool:
    raw = values.get(name, "true" if default else "false").strip().lower()
    if raw not in {"true", "false"}:
        raise RuntimeError(f"{name} must be true or false")
    return raw == "true"


def _parse_resolutions(value: str) -> frozenset[Resolution]:
    try:
        resolutions = frozenset(
            Resolution(*(int(part) for part in item.lower().split("x", maxsplit=1)))
            for item in value.split(",")
        )
    except (TypeError, ValueError) as error:
        raise RuntimeError("VIDEO_APP_MODEL_RESOLUTIONS must use WIDTHxHEIGHT entries") from error
    if not resolutions:
        raise RuntimeError("VIDEO_APP_MODEL_RESOLUTIONS must not be empty")
    return resolutions


def _parse_frame_counts(value: str) -> frozenset[int]:
    try:
        frame_counts = frozenset(int(item) for item in value.split(","))
    except ValueError as error:
        raise RuntimeError("VIDEO_APP_MODEL_FRAME_COUNTS must contain integers") from error
    if not frame_counts or any(item <= 0 for item in frame_counts):
        raise RuntimeError("VIDEO_APP_MODEL_FRAME_COUNTS must contain positive integers")
    return frame_counts


def _read_environment_file(path: Path) -> dict[str, str]:
    if not path.is_absolute() or not path.is_file():
        raise RuntimeError("environment file must be an existing absolute file")
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise RuntimeError(f"invalid environment entry on line {line_number}")
        name, value = line.split("=", maxsplit=1)
        name = name.strip()
        if not name or not name.replace("_", "a").isalnum() or not name[0].isalpha():
            raise RuntimeError(f"invalid environment name on line {line_number}")
        values[name] = value.strip()
    return values


@dataclass(frozen=True, slots=True)
class Wan21RuntimeSettings:
    """Worker-only paths and pins for the external Wan2.1 runtime."""

    repository_root: Path
    checkpoint_dir: Path
    python_executable: Path
    task: str
    model_revision: str

    def __post_init__(self) -> None:
        for path, field in (
            (self.repository_root, "VIDEO_APP_WAN21_REPOSITORY_ROOT"),
            (self.checkpoint_dir, "VIDEO_APP_WAN21_CHECKPOINT_DIR"),
            (self.python_executable, "VIDEO_APP_WAN21_PYTHON"),
        ):
            if not path.is_absolute():
                raise ValueError(f"{field} must be absolute")
        if not self.task or self.task.isspace():
            raise ValueError("VIDEO_APP_WAN21_TASK must not be empty")
        if not self.model_revision or self.model_revision.isspace():
            raise ValueError("VIDEO_APP_WAN21_MODEL_REVISION must not be empty")


@dataclass(frozen=True, slots=True)
class Wan22RuntimeSettings:
    """Qualified worker-only paths and pins for external Wan2.2 TI2V."""

    repository_root: Path
    checkpoint_dir: Path
    python_executable: Path
    qualification_report: Path
    checkpoint_manifest_sha256: str
    minimum_free_disk_bytes: int
    minimum_free_vram_bytes: int
    deadline_seconds: int

    def __post_init__(self) -> None:
        for path, field in (
            (self.repository_root, "VIDEO_APP_WAN22_REPOSITORY_ROOT"),
            (self.checkpoint_dir, "VIDEO_APP_WAN22_CHECKPOINT_DIR"),
            (self.python_executable, "VIDEO_APP_WAN22_PYTHON"),
            (self.qualification_report, "VIDEO_APP_WAN22_QUALIFICATION_REPORT"),
        ):
            if not path.is_absolute():
                raise ValueError(f"{field} must be absolute")
        if len(self.checkpoint_manifest_sha256) != 64 or any(
            item not in "0123456789abcdef" for item in self.checkpoint_manifest_sha256
        ):
            raise ValueError("VIDEO_APP_WAN22_CHECKPOINT_MANIFEST_SHA256 must be lowercase SHA-256")
        if (
            min(
                self.minimum_free_disk_bytes,
                self.minimum_free_vram_bytes,
                self.deadline_seconds,
            )
            <= 0
        ):
            raise ValueError("Wan2.2 qualification resource limits must be positive")


@dataclass(frozen=True, slots=True)
class ControlledRuntimeSettings:
    """Qualified worker-only paths for a VACE or Wan Animate runtime."""

    repository_root: Path
    checkpoint_dir: Path
    python_executable: Path
    qualification_report: Path
    checkpoint_manifest_sha256: str
    ffmpeg_executable: Path
    ffmpeg_sha256: str
    ffmpeg_version_line: str
    minimum_free_disk_bytes: int
    minimum_free_vram_bytes: int
    deadline_seconds: int

    def __post_init__(self) -> None:
        paths = (
            (self.repository_root, "controlled repository root", True),
            (self.checkpoint_dir, "controlled checkpoint directory", True),
            (self.python_executable, "controlled Python", False),
            (self.qualification_report, "controlled qualification report", False),
            (self.ffmpeg_executable, "controlled FFmpeg", False),
        )
        for path, field, directory in paths:
            attributes = getattr(path.lstat(), "st_file_attributes", 0) if path.exists() else 0
            correct_type = path.is_dir() if directory else path.is_file()
            if (
                not path.is_absolute()
                or not correct_type
                or path.is_symlink()
                or bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
            ):
                expected = "directory" if directory else "file"
                raise ValueError(f"{field} must be an existing absolute regular {expected}")
        for value, field in (
            (self.checkpoint_manifest_sha256, "checkpoint manifest"),
            (self.ffmpeg_sha256, "FFmpeg checksum"),
        ):
            if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
                raise ValueError(f"{field} must be lowercase SHA-256")
        if not self.ffmpeg_version_line.startswith("ffmpeg version "):
            raise ValueError("controlled FFmpeg version line must be exact")
        if (
            min(
                self.minimum_free_disk_bytes,
                self.minimum_free_vram_bytes,
                self.deadline_seconds,
            )
            <= 0
        ):
            raise ValueError("controlled runtime limits must be positive")


def _load_wan22_qualification(path: Path, checkpoint_sha256: str) -> dict[str, int]:
    attributes = getattr(path.lstat(), "st_file_attributes", 0) if path.exists() else 0
    if (
        not path.is_absolute()
        or not path.is_file()
        or path.is_symlink()
        or bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
    ):
        raise RuntimeError("VIDEO_APP_WAN22_QUALIFICATION_REPORT must be an existing absolute file")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("Wan2.2 qualification report must be valid JSON") from error
    required = {
        "status": "approved",
        "code_revision": "1ea34ff48f87168174e12956e200b1d908b1c5ff",
        "model_revision": "921dbaf3f1674a56f47e83fb80a34bac8a8f203e",
        "task": "ti2v-5B",
        "checkpoint_manifest_sha256": checkpoint_sha256,
        "input_conditioning_verified": True,
        "no_t2v_fallback_verified": True,
        "cancellation_cleanup_verified": True,
    }
    if not isinstance(payload, dict) or any(
        payload.get(key) != value for key, value in required.items()
    ):
        raise RuntimeError(
            "Wan2.2 qualification report does not match the required pins and evidence"
        )
    limits: dict[str, int] = {}
    for name in ("minimum_free_disk_bytes", "minimum_free_vram_bytes"):
        value = payload.get(name)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise RuntimeError(f"Wan2.2 qualification report {name} must be a positive integer")
        limits[name] = value
    return limits


def _load_controlled_qualification(
    path: Path,
    *,
    code_revision: str,
    model_revision: str,
    task: str,
    checkpoint_sha256: str,
    ffmpeg_sha256: str,
    ffmpeg_version_line: str,
    operations: tuple[str, ...],
) -> dict[str, int]:
    attributes = getattr(path.lstat(), "st_file_attributes", 0) if path.exists() else 0
    if (
        not path.is_absolute()
        or not path.is_file()
        or path.is_symlink()
        or bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
    ):
        raise RuntimeError("controlled qualification report must be an existing absolute file")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("controlled qualification report must be valid JSON") from error
    required: dict[str, object] = {
        "status": "approved",
        "code_revision": code_revision,
        "model_revision": model_revision,
        "task": task,
        "checkpoint_manifest_sha256": checkpoint_sha256,
        "ffmpeg_sha256": ffmpeg_sha256,
        "ffmpeg_version_line": ffmpeg_version_line,
        "operations": list(operations),
        "starting_frame_conditioning_verified": True,
        "reference_video_trim_verified": True,
        "constraint_plan_verified": True,
        "control_derivatives_verified": True,
        "cancellation_cleanup_verified": True,
    }
    if not isinstance(payload, dict) or any(
        payload.get(key) != value for key, value in required.items()
    ):
        raise RuntimeError("controlled qualification report does not match required evidence")
    limits: dict[str, int] = {}
    for name in ("minimum_free_disk_bytes", "minimum_free_vram_bytes"):
        value = payload.get(name)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise RuntimeError(f"controlled qualification report {name} must be positive")
        limits[name] = value
    return limits


@dataclass(frozen=True, slots=True)
class MediaRuntimeSettings:
    ffprobe_executable: Path
    ffprobe_sha256: str
    ffprobe_version_line: str
    timeout_seconds: int
    max_output_bytes: int

    def __post_init__(self) -> None:
        if not self.ffprobe_executable.is_absolute() or not self.ffprobe_executable.is_file():
            raise ValueError("VIDEO_APP_FFPROBE_EXECUTABLE must be an existing absolute file")
        if len(self.ffprobe_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.ffprobe_sha256
        ):
            raise ValueError("VIDEO_APP_FFPROBE_SHA256 must be lowercase SHA-256")
        if not self.ffprobe_version_line.startswith("ffprobe version "):
            raise ValueError("VIDEO_APP_FFPROBE_VERSION_LINE must be the exact first version line")
        if self.timeout_seconds <= 0 or self.max_output_bytes <= 0:
            raise ValueError("ffprobe limits must be positive")


@dataclass(frozen=True, slots=True)
class RoughCutRuntimeSettings:
    qualification_report: Path
    ffmpeg_executable: Path
    ffmpeg_sha256: str
    ffmpeg_version_line: str
    width: int
    height: int
    fps_numerator: int
    fps_denominator: int
    deadline_seconds: int

    def __post_init__(self) -> None:
        for path, field in (
            (self.qualification_report, "rough-cut qualification report"),
            (self.ffmpeg_executable, "rough-cut FFmpeg executable"),
        ):
            attributes = getattr(path.lstat(), "st_file_attributes", 0) if path.exists() else 0
            if (
                not path.is_absolute()
                or not path.is_file()
                or path.is_symlink()
                or bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
            ):
                raise ValueError(f"{field} must be an existing absolute regular file")
        if len(self.ffmpeg_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.ffmpeg_sha256
        ):
            raise ValueError("rough-cut FFmpeg checksum must be lowercase SHA-256")
        if not self.ffmpeg_version_line.startswith("ffmpeg version "):
            raise ValueError("rough-cut FFmpeg version line must be exact")
        if (
            min(
                self.width,
                self.height,
                self.fps_numerator,
                self.fps_denominator,
                self.deadline_seconds,
            )
            <= 0
        ):
            raise ValueError("rough-cut runtime settings must be positive")


@dataclass(frozen=True, slots=True)
class TimelineRenderRuntimeSettings:
    qualification_report: Path
    ffmpeg_executable: Path
    ffmpeg_sha256: str
    ffmpeg_version_line: str
    font_file: Path
    font_sha256: str
    font_family: str
    width: int
    height: int
    fps_numerator: int
    fps_denominator: int
    duration_ms: int
    deadline_seconds: int

    def __post_init__(self) -> None:
        for path, field in (
            (self.qualification_report, "timeline-render qualification report"),
            (self.ffmpeg_executable, "timeline-render FFmpeg executable"),
            (self.font_file, "timeline-render font file"),
        ):
            attributes = getattr(path.lstat(), "st_file_attributes", 0) if path.exists() else 0
            if (
                not path.is_absolute()
                or not path.is_file()
                or path.is_symlink()
                or bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
            ):
                raise ValueError(f"{field} must be an existing absolute regular file")
        for value, field in (
            (self.ffmpeg_sha256, "timeline-render FFmpeg checksum"),
            (self.font_sha256, "timeline-render font checksum"),
        ):
            if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
                raise ValueError(f"{field} must be lowercase SHA-256")
        if not self.ffmpeg_version_line.startswith("ffmpeg version "):
            raise ValueError("timeline-render FFmpeg version line must be exact")
        if re.fullmatch(r"[A-Za-z0-9 _-]{1,80}", self.font_family) is None:
            raise ValueError("timeline-render font family is invalid")
        if (
            min(
                self.width,
                self.height,
                self.fps_numerator,
                self.fps_denominator,
                self.duration_ms,
                self.deadline_seconds,
            )
            <= 0
        ):
            raise ValueError("timeline-render runtime settings must be positive")


def _load_rough_cut_qualification(
    path: Path,
    *,
    ffmpeg_sha256: str,
    ffmpeg_version_line: str,
    ffprobe_sha256: str,
    ffprobe_version_line: str,
    width: int,
    height: int,
    fps_numerator: int,
    fps_denominator: int,
) -> None:
    attributes = getattr(path.lstat(), "st_file_attributes", 0) if path.exists() else 0
    if (
        not path.is_absolute()
        or not path.is_file()
        or path.is_symlink()
        or bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
    ):
        raise RuntimeError("rough-cut qualification report must be an existing absolute file")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("rough-cut qualification report must be valid JSON") from error
    required: dict[str, object] = {
        "status": "approved",
        "backend_revision": "ffmpeg-rough-cut-v1",
        "ffmpeg_sha256": ffmpeg_sha256,
        "ffmpeg_version_line": ffmpeg_version_line,
        "ffprobe_sha256": ffprobe_sha256,
        "ffprobe_version_line": ffprobe_version_line,
        "width": width,
        "height": height,
        "fps_numerator": fps_numerator,
        "fps_denominator": fps_denominator,
        "image_audio_export_verified": True,
        "measured_output_verified": True,
        "input_hash_enforcement_verified": True,
        "cancellation_cleanup_verified": True,
    }
    if not isinstance(payload, dict) or any(
        payload.get(key) != value for key, value in required.items()
    ):
        raise RuntimeError("rough-cut qualification report does not match required evidence")


def _load_timeline_render_qualification(
    path: Path,
    *,
    ffmpeg_sha256: str,
    ffmpeg_version_line: str,
    ffprobe_sha256: str,
    ffprobe_version_line: str,
    font_sha256: str,
    font_family: str,
    width: int,
    height: int,
    fps_numerator: int,
    fps_denominator: int,
    duration_ms: int,
) -> None:
    attributes = getattr(path.lstat(), "st_file_attributes", 0) if path.exists() else 0
    if (
        not path.is_absolute()
        or not path.is_file()
        or path.is_symlink()
        or bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
    ):
        raise RuntimeError("timeline-render qualification report must be an absolute file")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("timeline-render qualification report must be valid JSON") from error
    required: dict[str, object] = {
        "status": "approved",
        "backend_revision": "ffmpeg-timeline-render-v1",
        "ffmpeg_sha256": ffmpeg_sha256,
        "ffmpeg_version_line": ffmpeg_version_line,
        "ffprobe_sha256": ffprobe_sha256,
        "ffprobe_version_line": ffprobe_version_line,
        "font_sha256": font_sha256,
        "font_family": font_family,
        "width": width,
        "height": height,
        "fps_numerator": fps_numerator,
        "fps_denominator": fps_denominator,
        "duration_ms": duration_ms,
        "title_caption_verified": True,
        "telugu_glyphs_verified": True,
        "audio_mix_verified": True,
        "measured_output_verified": True,
        "input_hash_enforcement_verified": True,
        "cancellation_cleanup_verified": True,
    }
    if not isinstance(payload, dict) or any(
        payload.get(key) != value for key, value in required.items()
    ):
        raise RuntimeError("timeline-render qualification report does not match required evidence")


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    database: DatabaseSettings
    data_root: Path
    queue_capacity: int
    cursor_secret: bytes
    capability: ModelCapability
    lease_duration: timedelta
    heartbeat_interval: timedelta
    poll_interval_seconds: float
    backend_name: str
    wan21: Wan21RuntimeSettings | None
    wan22: Wan22RuntimeSettings | None = None
    vace: ControlledRuntimeSettings | None = None
    animate: ControlledRuntimeSettings | None = None
    owner_id: str = "local-owner"
    max_upload_bytes: int = 50 * 1024 * 1024
    media: MediaRuntimeSettings | None = None
    rough_cut: RoughCutRuntimeSettings | None = None
    timeline_render: TimelineRenderRuntimeSettings | None = None

    def __post_init__(self) -> None:
        if not self.data_root.is_absolute():
            raise ValueError("VIDEO_APP_DATA_ROOT must be absolute")
        if self.queue_capacity <= 0:
            raise ValueError("queue_capacity must be positive")
        if len(self.cursor_secret) < 32:
            raise ValueError("VIDEO_APP_CURSOR_SECRET must contain at least 32 bytes")
        if self.lease_duration.total_seconds() <= 0:
            raise ValueError("lease_duration must be positive")
        if self.heartbeat_interval <= timedelta(0):
            raise ValueError("heartbeat_interval must be positive")
        if self.heartbeat_interval >= self.lease_duration / 3:
            raise ValueError("heartbeat_interval must be less than one third of lease_duration")
        if self.poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        if self.backend_name not in {
            "fake",
            "wan21",
            "wan22",
            "vace",
            "wan22-animate",
            "ffmpeg-rough-cut",
            "ffmpeg-timeline-render",
        }:
            raise ValueError(
                "VIDEO_APP_BACKEND must be fake, wan21, wan22, vace, or wan22-animate; "
                "ffmpeg-rough-cut and ffmpeg-timeline-render are media workers"
            )
        if (self.backend_name == "wan21") != (self.wan21 is not None):
            raise ValueError("Wan2.1 settings must be present only for the wan21 backend")
        if self.backend_name == "wan22" and self.wan22 is None:
            raise ValueError("qualified Wan2.2 settings are required for the wan22 backend")
        if self.backend_name == "vace" and self.vace is None:
            raise ValueError("qualified VACE settings are required for the vace backend")
        if self.backend_name == "wan22-animate" and self.animate is None:
            raise ValueError("qualified Animate settings are required for the Animate backend")
        if self.backend_name == "ffmpeg-rough-cut" and self.rough_cut is None:
            raise ValueError("qualified rough-cut settings are required for the FFmpeg backend")
        if self.backend_name == "ffmpeg-timeline-render" and self.timeline_render is None:
            raise ValueError("qualified timeline-render settings are required for the backend")
        if not self.owner_id or self.owner_id.isspace():
            raise ValueError("VIDEO_APP_OWNER_ID must not be empty")
        if self.max_upload_bytes <= 0:
            raise ValueError("VIDEO_APP_MAX_UPLOAD_BYTES must be positive")

    @classmethod
    def from_environment(cls) -> RuntimeSettings:
        return cls.from_values(os.environ)

    @classmethod
    def from_file(cls, path: Path) -> RuntimeSettings:
        return cls.from_values(_read_environment_file(path))

    @classmethod
    def from_values(cls, values: Mapping[str, str]) -> RuntimeSettings:
        data_root = Path(_required(values, "VIDEO_APP_DATA_ROOT"))
        cursor_secret = _required(values, "VIDEO_APP_CURSOR_SECRET").encode("utf-8")
        backend_name = _required(values, "VIDEO_APP_BACKEND")
        if backend_name not in {
            "fake",
            "wan21",
            "wan22",
            "vace",
            "wan22-animate",
            "ffmpeg-rough-cut",
            "ffmpeg-timeline-render",
        }:
            raise ValueError(
                "VIDEO_APP_BACKEND must be fake, wan21, wan22, vace, or wan22-animate; "
                "ffmpeg-rough-cut and ffmpeg-timeline-render are media workers"
            )
        wan21 = (
            Wan21RuntimeSettings(
                repository_root=Path(_required(values, "VIDEO_APP_WAN21_REPOSITORY_ROOT")),
                checkpoint_dir=Path(_required(values, "VIDEO_APP_WAN21_CHECKPOINT_DIR")),
                python_executable=Path(_required(values, "VIDEO_APP_WAN21_PYTHON")),
                task=_required(values, "VIDEO_APP_WAN21_TASK"),
                model_revision=_required(values, "VIDEO_APP_WAN21_MODEL_REVISION"),
            )
            if backend_name == "wan21"
            else None
        )
        wan22_enabled = _boolean(values, "VIDEO_APP_WAN22_TI2V_ENABLED")
        if backend_name == "wan22" and not wan22_enabled:
            raise RuntimeError("VIDEO_APP_WAN22_TI2V_ENABLED must be true for the wan22 backend")
        wan22 = None
        if wan22_enabled:
            checkpoint_sha256 = _required(values, "VIDEO_APP_WAN22_CHECKPOINT_MANIFEST_SHA256")
            report = Path(_required(values, "VIDEO_APP_WAN22_QUALIFICATION_REPORT"))
            limits = _load_wan22_qualification(report, checkpoint_sha256)
            wan22 = Wan22RuntimeSettings(
                repository_root=Path(_required(values, "VIDEO_APP_WAN22_REPOSITORY_ROOT")),
                checkpoint_dir=Path(_required(values, "VIDEO_APP_WAN22_CHECKPOINT_DIR")),
                python_executable=Path(_required(values, "VIDEO_APP_WAN22_PYTHON")),
                qualification_report=report,
                checkpoint_manifest_sha256=checkpoint_sha256,
                minimum_free_disk_bytes=limits["minimum_free_disk_bytes"],
                minimum_free_vram_bytes=limits["minimum_free_vram_bytes"],
                deadline_seconds=_positive_int(values, "VIDEO_APP_WAN22_DEADLINE_SECONDS", 7200),
            )
        controlled_ffmpeg_names = (
            "VIDEO_APP_CONTROLLED_FFMPEG_EXECUTABLE",
            "VIDEO_APP_CONTROLLED_FFMPEG_SHA256",
            "VIDEO_APP_CONTROLLED_FFMPEG_VERSION_LINE",
        )
        controlled_ffmpeg_configured = [
            name for name in controlled_ffmpeg_names if values.get(name, "").strip()
        ]
        if controlled_ffmpeg_configured and len(controlled_ffmpeg_configured) != 3:
            raise RuntimeError("all VIDEO_APP_CONTROLLED_FFMPEG_* values are required together")
        vace_enabled = _boolean(values, "VIDEO_APP_VACE_ENABLED")
        animate_enabled = _boolean(values, "VIDEO_APP_WAN_ANIMATE_ENABLED")
        if (vace_enabled or animate_enabled) and len(controlled_ffmpeg_configured) != 3:
            raise RuntimeError("controlled runtimes require qualified FFmpeg configuration")
        ffmpeg_path = Path(values.get("VIDEO_APP_CONTROLLED_FFMPEG_EXECUTABLE", ""))
        ffmpeg_sha256 = values.get("VIDEO_APP_CONTROLLED_FFMPEG_SHA256", "").strip()
        ffmpeg_version_line = values.get("VIDEO_APP_CONTROLLED_FFMPEG_VERSION_LINE", "").strip()

        def controlled_settings(
            prefix: str,
            *,
            code_revision: str,
            model_revision: str,
            task: str,
            operations: tuple[str, ...],
        ) -> ControlledRuntimeSettings:
            checkpoint_sha = _required(values, f"{prefix}_CHECKPOINT_MANIFEST_SHA256")
            report = Path(_required(values, f"{prefix}_QUALIFICATION_REPORT"))
            limits = _load_controlled_qualification(
                report,
                code_revision=code_revision,
                model_revision=model_revision,
                task=task,
                checkpoint_sha256=checkpoint_sha,
                ffmpeg_sha256=ffmpeg_sha256,
                ffmpeg_version_line=ffmpeg_version_line,
                operations=operations,
            )
            return ControlledRuntimeSettings(
                repository_root=Path(_required(values, f"{prefix}_REPOSITORY_ROOT")),
                checkpoint_dir=Path(_required(values, f"{prefix}_CHECKPOINT_DIR")),
                python_executable=Path(_required(values, f"{prefix}_PYTHON")),
                qualification_report=report,
                checkpoint_manifest_sha256=checkpoint_sha,
                ffmpeg_executable=ffmpeg_path,
                ffmpeg_sha256=ffmpeg_sha256,
                ffmpeg_version_line=ffmpeg_version_line,
                minimum_free_disk_bytes=limits["minimum_free_disk_bytes"],
                minimum_free_vram_bytes=limits["minimum_free_vram_bytes"],
                deadline_seconds=_positive_int(values, f"{prefix}_DEADLINE_SECONDS", 7200),
            )

        vace = (
            controlled_settings(
                "VIDEO_APP_VACE",
                code_revision="48eb44f1c4be87cc65a98bff985a26976841e9f3",
                model_revision="c76cda849bfb74d563b95f3db039421e9df2a570",
                task="animate_anything:salientbboxtrack",
                operations=("vace_performance_transfer",),
            )
            if vace_enabled
            else None
        )
        animate = (
            controlled_settings(
                "VIDEO_APP_WAN_ANIMATE",
                code_revision="29d4a35d32273d5309a3a95250bd4e118d8789b2",
                model_revision="cb93a225fbaf1ca100f54e79da8f994995b689b3",
                task="animate-14B",
                operations=("animate_character", "animate_replacement"),
            )
            if animate_enabled
            else None
        )
        if backend_name == "vace" and not vace_enabled:
            raise RuntimeError("VIDEO_APP_VACE_ENABLED must be true for the vace backend")
        if backend_name == "wan22-animate" and not animate_enabled:
            raise RuntimeError("VIDEO_APP_WAN_ANIMATE_ENABLED must be true for the Animate backend")
        capability = ModelCapability(
            model_id=_required(values, "VIDEO_APP_MODEL_ID"),
            display_name=_required(values, "VIDEO_APP_MODEL_DISPLAY_NAME"),
            modes=frozenset({GenerationMode.TEXT_TO_VIDEO}),
            resolutions=_parse_resolutions(_required(values, "VIDEO_APP_MODEL_RESOLUTIONS")),
            frame_counts=_parse_frame_counts(_required(values, "VIDEO_APP_MODEL_FRAME_COUNTS")),
        )
        media_names = (
            "VIDEO_APP_FFPROBE_EXECUTABLE",
            "VIDEO_APP_FFPROBE_SHA256",
            "VIDEO_APP_FFPROBE_VERSION_LINE",
        )
        configured_media_names = [name for name in media_names if values.get(name, "").strip()]
        if configured_media_names and len(configured_media_names) != len(media_names):
            raise RuntimeError("all VIDEO_APP_FFPROBE_* pin values must be configured together")
        media = (
            MediaRuntimeSettings(
                ffprobe_executable=Path(_required(values, "VIDEO_APP_FFPROBE_EXECUTABLE")),
                ffprobe_sha256=_required(values, "VIDEO_APP_FFPROBE_SHA256"),
                ffprobe_version_line=_required(values, "VIDEO_APP_FFPROBE_VERSION_LINE"),
                timeout_seconds=_positive_int(values, "VIDEO_APP_FFPROBE_TIMEOUT_SECONDS", 30),
                max_output_bytes=_positive_int(
                    values, "VIDEO_APP_FFPROBE_MAX_OUTPUT_BYTES", 2 * 1024 * 1024
                ),
            )
            if configured_media_names
            else None
        )
        rough_cut_enabled = _boolean(values, "VIDEO_APP_ROUGH_CUT_ENABLED")
        if backend_name == "ffmpeg-rough-cut" and not rough_cut_enabled:
            raise RuntimeError(
                "VIDEO_APP_ROUGH_CUT_ENABLED must be true for the FFmpeg rough-cut backend"
            )
        rough_cut = None
        if rough_cut_enabled:
            if media is None:
                raise RuntimeError("rough-cut rendering requires qualified ffprobe configuration")
            report = Path(_required(values, "VIDEO_APP_ROUGH_CUT_QUALIFICATION_REPORT"))
            ffmpeg_path = Path(_required(values, "VIDEO_APP_ROUGH_CUT_FFMPEG_EXECUTABLE"))
            ffmpeg_sha256 = _required(values, "VIDEO_APP_ROUGH_CUT_FFMPEG_SHA256")
            ffmpeg_version_line = _required(values, "VIDEO_APP_ROUGH_CUT_FFMPEG_VERSION_LINE")
            width = _positive_int(values, "VIDEO_APP_ROUGH_CUT_WIDTH", 1280)
            height = _positive_int(values, "VIDEO_APP_ROUGH_CUT_HEIGHT", 720)
            fps_numerator = _positive_int(values, "VIDEO_APP_ROUGH_CUT_FPS_NUMERATOR", 24)
            fps_denominator = _positive_int(values, "VIDEO_APP_ROUGH_CUT_FPS_DENOMINATOR", 1)
            _load_rough_cut_qualification(
                report,
                ffmpeg_sha256=ffmpeg_sha256,
                ffmpeg_version_line=ffmpeg_version_line,
                ffprobe_sha256=media.ffprobe_sha256,
                ffprobe_version_line=media.ffprobe_version_line,
                width=width,
                height=height,
                fps_numerator=fps_numerator,
                fps_denominator=fps_denominator,
            )
            rough_cut = RoughCutRuntimeSettings(
                qualification_report=report,
                ffmpeg_executable=ffmpeg_path,
                ffmpeg_sha256=ffmpeg_sha256,
                ffmpeg_version_line=ffmpeg_version_line,
                width=width,
                height=height,
                fps_numerator=fps_numerator,
                fps_denominator=fps_denominator,
                deadline_seconds=_positive_int(
                    values, "VIDEO_APP_ROUGH_CUT_DEADLINE_SECONDS", 7200
                ),
            )
        timeline_render_enabled = _boolean(values, "VIDEO_APP_TIMELINE_RENDER_ENABLED")
        if backend_name == "ffmpeg-timeline-render" and not timeline_render_enabled:
            raise RuntimeError(
                "VIDEO_APP_TIMELINE_RENDER_ENABLED must be true for the timeline backend"
            )
        timeline_render = None
        if timeline_render_enabled:
            if media is None:
                raise RuntimeError("timeline rendering requires qualified ffprobe configuration")
            report = Path(_required(values, "VIDEO_APP_TIMELINE_RENDER_QUALIFICATION_REPORT"))
            timeline_ffmpeg = Path(_required(values, "VIDEO_APP_TIMELINE_RENDER_FFMPEG_EXECUTABLE"))
            timeline_ffmpeg_sha256 = _required(values, "VIDEO_APP_TIMELINE_RENDER_FFMPEG_SHA256")
            timeline_ffmpeg_version = _required(
                values, "VIDEO_APP_TIMELINE_RENDER_FFMPEG_VERSION_LINE"
            )
            font_file = Path(_required(values, "VIDEO_APP_TIMELINE_RENDER_FONT_FILE"))
            font_sha256 = _required(values, "VIDEO_APP_TIMELINE_RENDER_FONT_SHA256")
            font_family = _required(values, "VIDEO_APP_TIMELINE_RENDER_FONT_FAMILY")
            width = _positive_int(values, "VIDEO_APP_TIMELINE_RENDER_WIDTH", 1280)
            height = _positive_int(values, "VIDEO_APP_TIMELINE_RENDER_HEIGHT", 720)
            fps_numerator = _positive_int(values, "VIDEO_APP_TIMELINE_RENDER_FPS_NUMERATOR", 24)
            fps_denominator = _positive_int(values, "VIDEO_APP_TIMELINE_RENDER_FPS_DENOMINATOR", 1)
            duration_ms = _positive_int(values, "VIDEO_APP_TIMELINE_RENDER_DURATION_MS", 900_000)
            _load_timeline_render_qualification(
                report,
                ffmpeg_sha256=timeline_ffmpeg_sha256,
                ffmpeg_version_line=timeline_ffmpeg_version,
                ffprobe_sha256=media.ffprobe_sha256,
                ffprobe_version_line=media.ffprobe_version_line,
                font_sha256=font_sha256,
                font_family=font_family,
                width=width,
                height=height,
                fps_numerator=fps_numerator,
                fps_denominator=fps_denominator,
                duration_ms=duration_ms,
            )
            timeline_render = TimelineRenderRuntimeSettings(
                qualification_report=report,
                ffmpeg_executable=timeline_ffmpeg,
                ffmpeg_sha256=timeline_ffmpeg_sha256,
                ffmpeg_version_line=timeline_ffmpeg_version,
                font_file=font_file,
                font_sha256=font_sha256,
                font_family=font_family,
                width=width,
                height=height,
                fps_numerator=fps_numerator,
                fps_denominator=fps_denominator,
                duration_ms=duration_ms,
                deadline_seconds=_positive_int(
                    values, "VIDEO_APP_TIMELINE_RENDER_DEADLINE_SECONDS", 14_400
                ),
            )
        return cls(
            database=DatabaseSettings(_required(values, "DATABASE_URL")),
            data_root=data_root,
            queue_capacity=_positive_int(values, "VIDEO_APP_QUEUE_CAPACITY", 10),
            cursor_secret=cursor_secret,
            capability=capability,
            lease_duration=timedelta(seconds=_positive_int(values, "VIDEO_APP_LEASE_SECONDS", 60)),
            heartbeat_interval=timedelta(
                seconds=_positive_int(values, "VIDEO_APP_HEARTBEAT_SECONDS", 10)
            ),
            poll_interval_seconds=float(_positive_int(values, "VIDEO_APP_POLL_SECONDS", 2)),
            backend_name=backend_name,
            wan21=wan21,
            wan22=wan22,
            vace=vace,
            animate=animate,
            owner_id=values.get("VIDEO_APP_OWNER_ID", "local-owner").strip(),
            max_upload_bytes=_positive_int(values, "VIDEO_APP_MAX_UPLOAD_BYTES", 50 * 1024 * 1024),
            media=media,
            rough_cut=rough_cut,
            timeline_render=timeline_render,
        )


@dataclass(frozen=True, slots=True)
class StaticCapabilityProvider:
    items: tuple[ModelCapability, ...]

    def capabilities(self) -> tuple[ModelCapability, ...]:
        return self.items


class UtcClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class SecureIdentifiers:
    def new_asset_id(self) -> str:
        return f"asset_{uuid4().hex}"

    def new_library_entity_id(self) -> str:
        return f"library_{uuid4().hex}"

    def new_library_version_id(self) -> str:
        return f"library_version_{uuid4().hex}"

    def new_film_bible_snapshot_id(self) -> str:
        return f"film_bible_{uuid4().hex}"

    def new_shot_binding_revision_id(self) -> str:
        return f"shot_binding_{uuid4().hex}"

    def new_starting_frame_composition_id(self) -> str:
        return f"starting_frame_{uuid4().hex}"

    def new_reference_video_guidance_id(self) -> str:
        return f"reference_guidance_{uuid4().hex}"

    def new_timeline_id(self) -> str:
        return f"timeline_{uuid4().hex}"

    def new_scene_id(self) -> str:
        return f"scene_{uuid4().hex}"

    def new_shot_id(self) -> str:
        return f"shot_{uuid4().hex}"

    def new_approval_id(self) -> str:
        return f"approval_{uuid4().hex}"

    def new_project_id(self) -> str:
        return f"project_{uuid4().hex}"

    def new_job_id(self) -> str:
        return f"job_{uuid4().hex}"

    def new_attempt_id(self) -> str:
        return f"attempt_{uuid4().hex}"

    def new_lease_token(self) -> str:
        return secrets.token_urlsafe(32)

    def new_correlation_id(self) -> str:
        return f"correlation_{uuid4().hex}"


class SecureSeedSource:
    def new_seed(self) -> int:
        return secrets.randbits(63)
