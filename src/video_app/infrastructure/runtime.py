"""Typed runtime settings and standard infrastructure primitives."""

from __future__ import annotations

import os
import secrets
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
        if self.backend_name != "fake":
            raise ValueError("only the fake backend is available in this runtime")

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
        capability = ModelCapability(
            model_id=_required(values, "VIDEO_APP_MODEL_ID"),
            display_name=_required(values, "VIDEO_APP_MODEL_DISPLAY_NAME"),
            modes=frozenset({GenerationMode.TEXT_TO_VIDEO}),
            resolutions=_parse_resolutions(_required(values, "VIDEO_APP_MODEL_RESOLUTIONS")),
            frame_counts=_parse_frame_counts(_required(values, "VIDEO_APP_MODEL_FRAME_COUNTS")),
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
            backend_name=_required(values, "VIDEO_APP_BACKEND"),
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
