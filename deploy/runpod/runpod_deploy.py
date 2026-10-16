"""Repeatable RunPod deployment, supervision, diagnosis, backup, and recovery.

This module deliberately uses only the Python standard library so it can validate and
bootstrap an installation before the application virtual environment exists. It never
imports application internals or owns product/runtime policy.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib
import json
import os
import re
import secrets
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn, Protocol, TextIO, cast


class FileControl(Protocol):
    LOCK_EX: int
    LOCK_NB: int
    LOCK_UN: int

    def flock(self, descriptor: int, operation: int) -> None: ...


FILE_CONTROL: FileControl | None
try:  # pragma: no cover - selected by the host platform
    FILE_CONTROL = cast(FileControl, importlib.import_module("fcntl"))
except ImportError:  # Windows can import the validation helpers in the unit suite.
    FILE_CONTROL = None

REPOSITORY_URL = "https://github.com/Rameshdandu1/video_factory_win.git"
EXPECTED_ORIGIN = "https://github.com/Rameshdandu1/video_factory_win"
REF_PATTERN = re.compile(r"^[0-9a-f]{40}$")
ENV_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
PLACEHOLDER_FRAGMENTS = ("change-this", "replace-with", "example.com", "<", ">")
APP_ROLE = "video_app"
APP_DATABASE = "video_factory"
SERVICE_NAMES = (
    "video-factory-postgres",
    "video-factory-api",
    "video-factory-worker",
    "video-factory-nginx",
    "video-factory-tailscaled",
)
MANAGED_PORTS = {
    "video-factory-postgres": 5432,
    "video-factory-api": 8000,
    "video-factory-nginx": 5173,
}
EXIT_CONFIGURATION = 3
EXIT_CONFLICT = 4
EXIT_DEPENDENCY = 5
EXIT_SERVICE = 6
EXIT_BACKUP = 7
EXIT_NETWORK = 8
HTTP_PROBE_BODY_LIMIT = 64 * 1024
FRONTEND_HTTP_MARKERS = ("<title>Video Factory</title>", '<div id="root"></div>')
API_HEALTH_RESPONSE = {"status": "ok"}

_RUNTIME_CONFIG_CHECK = """\
from pathlib import Path
import sys
from video_app.infrastructure.runtime import RuntimeSettings
RuntimeSettings.from_file(Path(sys.argv[1]))
"""


class DeploymentError(RuntimeError):
    """Expected operator-facing failure with a stable process exit code."""

    def __init__(self, message: str, *, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@dataclass(frozen=True, slots=True)
class DeploymentPaths:
    """Absolute filesystem layout for one RunPod installation."""

    install_root: Path
    config_root: Path
    state_root: Path
    log_root: Path
    run_root: Path

    def __post_init__(self) -> None:
        for value in asdict(self).values():
            if not isinstance(value, Path) or not value.is_absolute():
                raise ValueError("all deployment paths must be absolute")

    @property
    def releases_root(self) -> Path:
        return self.install_root / "releases"

    @property
    def current_root(self) -> Path:
        return self.install_root / "current"

    @property
    def env_file(self) -> Path:
        return self.config_root / "video-factory.env"

    @property
    def supervisor_config(self) -> Path:
        return self.config_root / "supervisord.conf"

    @property
    def nginx_config(self) -> Path:
        return self.config_root / "nginx.conf"

    @property
    def tailscale_config(self) -> Path:
        return self.config_root / "tailscaled.json"

    @property
    def deployment_manifest(self) -> Path:
        return self.state_root / "deployment.json"

    @property
    def postgres_data(self) -> Path:
        return self.state_root / "postgres"

    @property
    def postgres_socket_dir(self) -> Path:
        return self.run_root / "postgres"

    @property
    def application_data(self) -> Path:
        return self.state_root / "data"

    @property
    def tailscale_state(self) -> Path:
        return self.state_root / "tailscale"

    @property
    def tailscale_socket(self) -> Path:
        return self.run_root / "tailscaled.sock"

    @property
    def supervisor_socket(self) -> Path:
        return self.run_root / "supervisor.sock"

    @property
    def backup_root(self) -> Path:
        return self.state_root / "backups"

    @property
    def smoke_report(self) -> Path:
        return self.state_root / "last-smoke-test.json"

    @classmethod
    def from_environment(cls, values: Mapping[str, str] | None = None) -> DeploymentPaths:
        source = os.environ if values is None else values
        return cls(
            install_root=Path(source.get("VIDEO_FACTORY_INSTALL_ROOT", "/opt/video-factory")),
            config_root=Path(source.get("VIDEO_FACTORY_CONFIG_ROOT", "/etc/video-factory")),
            state_root=Path(source.get("VIDEO_FACTORY_STATE_ROOT", "/var/lib/video-factory")),
            log_root=Path(source.get("VIDEO_FACTORY_LOG_ROOT", "/var/log/video-factory")),
            run_root=Path(source.get("VIDEO_FACTORY_RUN_ROOT", "/run/video-factory")),
        )


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class CommandRunner:
    """Subprocess boundary that never logs commands or environment values."""

    def run(
        self,
        arguments: Sequence[str | Path],
        *,
        cwd: Path | None = None,
        environment: Mapping[str, str] | None = None,
        input_text: str | None = None,
        check: bool = True,
        capture: bool = True,
        timeout: float | None = None,
    ) -> CommandResult:
        try:
            completed = subprocess.run(
                [str(item) for item in arguments],
                cwd=cwd,
                env=None if environment is None else dict(environment),
                input=input_text,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=capture,
                check=False,
                timeout=timeout,
            )
        except FileNotFoundError as error:
            raise DeploymentError("A required executable is unavailable.", exit_code=5) from error
        except subprocess.TimeoutExpired as error:
            raise DeploymentError(
                "A required command exceeded its deadline.", exit_code=6
            ) from error
        result = CommandResult(completed.returncode, completed.stdout or "", completed.stderr or "")
        if check and result.returncode != 0:
            raise DeploymentError(
                "A required command failed. Inspect the dedicated deployment log for details.",
                exit_code=EXIT_SERVICE,
            )
        return result


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write(path: Path, content: str, *, mode: int) -> None:
    """Write and fsync a regular file before replacing its destination."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        os.chmod(path, mode)
    except BaseException:
        with contextlib.suppress(OSError):
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
        raise


def atomic_json(path: Path, payload: Mapping[str, Any], *, mode: int = 0o600) -> None:
    atomic_write(path, json.dumps(payload, sort_keys=True, indent=2) + "\n", mode=mode)


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DeploymentError(
            f"Deployment metadata is missing or invalid: {path.name}.",
            exit_code=EXIT_CONFIGURATION,
        ) from error
    if not isinstance(payload, dict):
        raise DeploymentError("Deployment metadata must be a JSON object.", exit_code=3)
    return payload


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse the application's literal KEY=VALUE format and reject ambiguous input."""

    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        raise DeploymentError(
            "The deployment environment file must be an existing absolute regular file.",
            exit_code=EXIT_CONFIGURATION,
        )
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise DeploymentError(
            "The deployment environment file cannot be read.", exit_code=EXIT_CONFIGURATION
        ) from error
    for line_number, raw_line in enumerate(lines, 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise DeploymentError(
                f"Invalid environment entry on line {line_number}.", exit_code=EXIT_CONFIGURATION
            )
        name, value = line.split("=", 1)
        name = name.strip()
        if not ENV_NAME_PATTERN.fullmatch(name):
            raise DeploymentError(
                f"Invalid environment name on line {line_number}.", exit_code=EXIT_CONFIGURATION
            )
        if name in values:
            raise DeploymentError(
                f"Duplicate environment key {name} on line {line_number}.",
                exit_code=EXIT_CONFIGURATION,
            )
        values[name] = value.strip()
    validate_environment_values(values)
    return values


def validate_environment_values(values: Mapping[str, str]) -> None:
    required = (
        "DATABASE_URL",
        "VIDEO_APP_DATA_ROOT",
        "VIDEO_APP_CURSOR_SECRET",
        "VIDEO_APP_BACKEND",
        "VIDEO_APP_OWNER_ID",
        "VIDEO_APP_MODEL_ID",
        "VIDEO_APP_MODEL_DISPLAY_NAME",
        "VIDEO_APP_MODEL_RESOLUTIONS",
        "VIDEO_APP_MODEL_FRAME_COUNTS",
    )
    for name in required:
        value = values.get(name, "")
        if not value:
            raise DeploymentError(f"{name} is required.", exit_code=EXIT_CONFIGURATION)
        if any(fragment in value.lower() for fragment in PLACEHOLDER_FRAGMENTS):
            raise DeploymentError(f"{name} contains a placeholder.", exit_code=EXIT_CONFIGURATION)
    parsed = urllib.parse.urlsplit(values["DATABASE_URL"])
    if parsed.scheme != "postgresql+asyncpg" or not parsed.hostname or not parsed.path.strip("/"):
        raise DeploymentError(
            "DATABASE_URL must use postgresql+asyncpg with a host and database.",
            exit_code=EXIT_CONFIGURATION,
        )
    user, _password, database, port = parse_database_url(values["DATABASE_URL"])
    if user != APP_ROLE or database != APP_DATABASE or port != 5432:
        raise DeploymentError(
            "DATABASE_URL must target the managed loopback application database.",
            exit_code=EXIT_CONFIGURATION,
        )
    data_root = Path(values["VIDEO_APP_DATA_ROOT"])
    if not data_root.is_absolute():
        raise DeploymentError("VIDEO_APP_DATA_ROOT must be absolute.", exit_code=3)
    if len(values["VIDEO_APP_CURSOR_SECRET"].encode("utf-8")) < 32:
        raise DeploymentError("VIDEO_APP_CURSOR_SECRET is too short.", exit_code=3)


def database_url(*, password: str, port: int = 5432) -> str:
    encoded_user = urllib.parse.quote(APP_ROLE, safe="")
    encoded_password = urllib.parse.quote(password, safe="")
    encoded_database = urllib.parse.quote(APP_DATABASE, safe="")
    return (
        f"postgresql+asyncpg://{encoded_user}:{encoded_password}"
        f"@127.0.0.1:{port}/{encoded_database}"
    )


def parse_database_url(url: str) -> tuple[str, str, str, int]:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "postgresql+asyncpg" or parsed.username is None:
        raise DeploymentError("Unsupported database URL.", exit_code=EXIT_CONFIGURATION)
    password = urllib.parse.unquote(parsed.password or "")
    database = urllib.parse.unquote(parsed.path.lstrip("/"))
    if not password or not database or parsed.hostname != "127.0.0.1":
        raise DeploymentError("Deployment database URL must target loopback.", exit_code=3)
    return urllib.parse.unquote(parsed.username), password, database, parsed.port or 5432


def database_url_with_name(url: str, database: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", database):
        raise DeploymentError("Unsafe database name.", exit_code=EXIT_CONFIGURATION)
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, f"/{urllib.parse.quote(database, safe='')}", "", "")
    )


def read_private_secret(path: Path, *, label: str) -> str:
    if not path.is_absolute():
        raise DeploymentError(f"{label} file path must be absolute.", exit_code=3)
    if path.is_symlink():
        raise DeploymentError(f"{label} file must not be a symbolic link.", exit_code=3)
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise DeploymentError(f"{label} file is unavailable.", exit_code=3) from error
    mode = stat.S_IMODE(resolved.stat().st_mode)
    if not resolved.is_file() or mode & 0o077:
        raise DeploymentError(
            f"{label} file must be a private regular file (mode 0600).", exit_code=3
        )
    value = resolved.read_text(encoding="utf-8").rstrip("\r\n")
    if not value or "\n" in value or "\r" in value or "\x00" in value:
        raise DeploymentError(f"{label} value is invalid.", exit_code=3)
    return value


def demo_environment(paths: DeploymentPaths, *, password: str, owner_id: str) -> dict[str, str]:
    return {
        "DATABASE_URL": database_url(password=password),
        "VIDEO_APP_DATA_ROOT": str(paths.application_data),
        "VIDEO_APP_CURSOR_SECRET": secrets.token_urlsafe(48),
        "VIDEO_APP_QUEUE_CAPACITY": "10",
        "VIDEO_APP_BACKEND": "fake",
        "VIDEO_APP_OWNER_ID": owner_id,
        "VIDEO_APP_MAX_UPLOAD_BYTES": "52428800",
        "VIDEO_APP_MODEL_ID": "wan21-t2v",
        "VIDEO_APP_MODEL_DISPLAY_NAME": "Wan2.1 Text to Video",
        "VIDEO_APP_MODEL_RESOLUTIONS": "832x480",
        "VIDEO_APP_MODEL_FRAME_COUNTS": "81",
        "VIDEO_APP_LEASE_SECONDS": "60",
        "VIDEO_APP_HEARTBEAT_SECONDS": "10",
        "VIDEO_APP_POLL_SECONDS": "2",
    }


def serialize_environment(values: Mapping[str, str]) -> str:
    """Serialize literal values without shell quoting because the app does not source this file."""

    for name, value in values.items():
        if (
            not ENV_NAME_PATTERN.fullmatch(name)
            or "\n" in value
            or "\r" in value
            or "\x00" in value
        ):
            raise DeploymentError("Environment values must be single-line literals.", exit_code=3)
    ordered = [f"{name}={values[name]}" for name in sorted(values)]
    return (
        "# Managed by scripts/runpodctl. This is not a shell script.\n" + "\n".join(ordered) + "\n"
    )


def normalize_origin(value: str) -> str:
    normalized = (
        value.strip().removesuffix(".git").replace("git@github.com:", "https://github.com/")
    )
    return normalized.rstrip("/")


def validate_origin(value: str) -> None:
    if normalize_origin(value) != EXPECTED_ORIGIN:
        raise DeploymentError(
            "The checkout origin is not Rameshdandu1/video_factory_win.",
            exit_code=EXIT_CONFLICT,
        )


def render_template(template: str, replacements: Mapping[str, str]) -> str:
    rendered = template
    for name, value in replacements.items():
        if "\n" in value or "\r" in value:
            raise DeploymentError("Configuration values must not contain newlines.", exit_code=3)
        rendered = rendered.replace(f"@@{name}@@", value)
    missing = sorted(set(re.findall(r"@@([A-Z0-9_]+)@@", rendered)))
    if missing:
        raise DeploymentError(
            f"Configuration template is missing values for: {', '.join(missing)}.", exit_code=3
        )
    return rendered


def ensure_safe_archive_members(members: Iterable[tarfile.TarInfo]) -> tuple[tarfile.TarInfo, ...]:
    safe: list[tarfile.TarInfo] = []
    names: set[str] = set()
    for member in members:
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk():
            raise DeploymentError("Backup archive contains an unsafe path or link.", exit_code=7)
        if not (member.isdir() or member.isfile()):
            raise DeploymentError("Backup archive contains an unsupported entry.", exit_code=7)
        if member.name in names:
            raise DeploymentError("Backup archive contains a duplicate entry.", exit_code=7)
        names.add(member.name)
        safe.append(member)
    return tuple(safe)


def redact_text(value: str, secrets_to_remove: Iterable[str]) -> str:
    redacted = value
    for secret_value in secrets_to_remove:
        if secret_value:
            redacted = redacted.replace(secret_value, "[REDACTED]")
    redacted = re.sub(
        r"postgresql(?:\+asyncpg)?://[^\s]+", "postgresql+asyncpg://[REDACTED]", redacted
    )
    redacted = re.sub(r"tskey-[A-Za-z0-9_-]+", "[REDACTED]", redacted)
    redacted = re.sub(r"https://login\.tailscale\.com/[^\s]+", "[REDACTED]", redacted)
    return redacted


def parse_listening_ports(output: str) -> dict[int, str]:
    """Return TCP listeners from ``ss -H -ltnp`` output without guessing ownership."""

    listeners: dict[int, str] = {}
    for line in output.splitlines():
        fields = line.split(maxsplit=5)
        if len(fields) < 4:
            continue
        address = fields[3].rsplit(":", 1)
        if len(address) != 2 or not address[1].isdigit():
            continue
        port = int(address[1])
        listeners[port] = fields[5] if len(fields) > 5 else "owner unavailable"
    return listeners


def tree_checksums(root: Path) -> dict[str, str]:
    """Hash regular files below a trusted root without following symlinks."""

    checksums: dict[str, str] = {}
    if not root.exists():
        return checksums
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise DeploymentError("Application data contains a symbolic link.", exit_code=7)
        if path.is_file():
            checksums[path.relative_to(root).as_posix()] = sha256_file(path)
    return checksums


def tree_size(root: Path) -> int:
    total = 0
    if not root.exists():
        return total
    for path in root.rglob("*"):
        if path.is_symlink():
            raise DeploymentError("Application data contains a symbolic link.", exit_code=7)
        if path.is_file():
            total += path.stat().st_size
    return total


def verify_tree_checksums(root: Path, expected: Mapping[str, str]) -> None:
    actual = tree_checksums(root)
    if actual != dict(expected):
        raise DeploymentError("Backup application-data checksums do not match.", exit_code=7)


def remove_tree_within(path: Path, root: Path) -> None:
    """Remove one verified deployment-owned directory without following a link."""

    if not path.exists():
        return
    if path.is_symlink() or not path.is_dir():
        raise DeploymentError("Cleanup target is not a deployment-owned directory.", exit_code=4)
    resolved_root = root.resolve(strict=True)
    resolved_path = path.resolve(strict=True)
    try:
        relative = resolved_path.relative_to(resolved_root)
    except ValueError as error:
        raise DeploymentError("Cleanup target escapes its managed root.", exit_code=4) from error
    if not relative.parts:
        raise DeploymentError("Refusing to remove a managed root directory.", exit_code=4)
    shutil.rmtree(resolved_path)


class InstallationLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle: TextIO | None = None

    def __enter__(self) -> InstallationLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+", encoding="utf-8")
        if FILE_CONTROL is not None:
            exclusive = FILE_CONTROL.LOCK_EX | FILE_CONTROL.LOCK_NB
            try:
                FILE_CONTROL.flock(self.handle.fileno(), exclusive)
            except BlockingIOError as error:
                self.handle.close()
                raise DeploymentError(
                    "Another deployment operation is running.", exit_code=4
                ) from error
        return self

    def __exit__(self, *_arguments: object) -> None:
        if self.handle is not None and FILE_CONTROL is not None:
            FILE_CONTROL.flock(self.handle.fileno(), FILE_CONTROL.LOCK_UN)
        if self.handle is not None:
            self.handle.close()


class DeploymentManager:
    """Own only deployment state and external process lifecycle."""

    def __init__(self, paths: DeploymentPaths, runner: CommandRunner | None = None) -> None:
        self.paths = paths
        self.runner = runner or CommandRunner()
        self.template_root = Path(__file__).resolve().parent

    def _require_root(self) -> None:
        if hasattr(os, "geteuid") and os.geteuid() != 0:
            raise DeploymentError(
                "RunPod installation and service management require root inside the Pod.",
                exit_code=EXIT_CONFIGURATION,
            )

    def _ensure_directories(self) -> None:
        for path, mode in (
            (self.paths.install_root, 0o755),
            (self.paths.releases_root, 0o755),
            (self.paths.config_root, 0o750),
            (self.paths.state_root, 0o710),
            (self.paths.application_data, 0o750),
            (self.paths.backup_root, 0o750),
            (self.paths.tailscale_state, 0o700),
            (self.paths.log_root, 0o750),
            (self.paths.run_root, 0o710),
            (self.paths.postgres_socket_dir, 0o700),
            (self.paths.install_root / "nginx", 0o750),
        ):
            if path.exists() and (path.is_symlink() or not path.is_dir()):
                raise DeploymentError(
                    f"Managed path is not a regular directory: {path.name}.", exit_code=4
                )
            path.mkdir(parents=True, exist_ok=True)
            os.chmod(path, mode)
        for path in (self.paths.state_root, self.paths.run_root):
            self._set_directory_owner(path, "root:postgres")
        self._set_directory_owner(self.paths.postgres_socket_dir, "postgres:postgres")

    def _set_directory_owner(self, path: Path, owner: str) -> None:
        self.runner.run(("/usr/bin/chown", owner, path))

    def _current_release(self) -> Path:
        current = self.paths.current_root
        if not current.is_symlink():
            raise DeploymentError("No active Video Factory release is installed.", exit_code=3)
        resolved = current.resolve(strict=True)
        try:
            resolved.relative_to(self.paths.releases_root.resolve(strict=True))
        except ValueError as error:
            raise DeploymentError(
                "The current release link escapes the releases root.", exit_code=3
            ) from error
        return resolved

    def _deployment(self) -> dict[str, Any]:
        return read_json(self.paths.deployment_manifest)

    def _supervisorctl(self, *arguments: str, check: bool = True) -> CommandResult:
        return self.runner.run(
            ("/usr/bin/supervisorctl", "-c", self.paths.supervisor_config, *arguments),
            check=check,
        )

    def _service_states(self) -> dict[str, str]:
        if not self.paths.supervisor_socket.exists():
            return {name: "STOPPED" for name in SERVICE_NAMES}
        try:
            result = self._supervisorctl("status", check=False)
        except DeploymentError:
            return {name: "UNAVAILABLE" for name in SERVICE_NAMES}
        states = {name: "UNKNOWN" for name in SERVICE_NAMES}
        for line in result.stdout.splitlines():
            fields = line.split()
            if len(fields) >= 2 and fields[0] in states:
                states[fields[0]] = fields[1]
        return states

    def _ensure_supervisor(self) -> None:
        if self.paths.supervisor_socket.exists():
            result = self._supervisorctl("pid", check=False)
            if result.returncode == 0:
                return
            self.paths.supervisor_socket.unlink(missing_ok=True)
        self.runner.run(("/usr/bin/supervisord", "-c", self.paths.supervisor_config))
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if self.paths.supervisor_socket.exists():
                result = self._supervisorctl("pid", check=False)
                if result.returncode == 0:
                    return
            time.sleep(0.25)
        raise DeploymentError("Supervisor did not create its private control socket.", exit_code=6)

    def _start_service(self, name: str) -> None:
        states = self._service_states()
        if states.get(name) == "RUNNING":
            return
        result = self._supervisorctl("start", name, check=False)
        if result.returncode != 0 or "ERROR" in result.stdout:
            raise DeploymentError(f"Supervisor could not start {name}.", exit_code=6)

    def _stop_service(self, name: str) -> None:
        if not self.paths.supervisor_socket.exists():
            return
        state = self._service_states().get(name)
        if state in {"STOPPED", "EXITED", "FATAL", "UNKNOWN"}:
            return
        self._supervisorctl("stop", name, check=False)

    def _wait_http(self, url: str, *, deadline_seconds: int = 30) -> None:
        deadline = time.monotonic() + deadline_seconds
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=2) as response:
                    if 200 <= response.status < 300:
                        return
            except (OSError, urllib.error.URLError):
                pass
            time.sleep(0.5)
        raise DeploymentError(f"Service readiness failed for {url}.", exit_code=6)

    def _postgres_bin(self, executable: str) -> Path:
        manifest = self._deployment() if self.paths.deployment_manifest.exists() else {}
        configured = manifest.get("postgres_bin_dir")
        if isinstance(configured, str):
            candidate = Path(configured) / executable
            if candidate.is_file():
                return candidate
        matches = sorted(Path("/usr/lib/postgresql").glob(f"*/bin/{executable}"), reverse=True)
        if not matches:
            fallback = shutil.which(executable)
            if fallback is None:
                raise DeploymentError(
                    f"PostgreSQL executable {executable} is unavailable.", exit_code=5
                )
            return Path(fallback)
        return matches[0]

    def _database_environment(self, values: Mapping[str, str]) -> dict[str, str]:
        user, password, database, port = parse_database_url(values["DATABASE_URL"])
        environment = dict(os.environ)
        environment.update(
            {
                "PGHOST": "127.0.0.1",
                "PGPORT": str(port),
                "PGUSER": user,
                "PGDATABASE": database,
                "PGPASSWORD": password,
                "DATABASE_URL": values["DATABASE_URL"],
            }
        )
        return environment

    def _wait_postgres(self, values: Mapping[str, str], *, deadline_seconds: int = 30) -> None:
        environment = self._database_environment(values)
        deadline = time.monotonic() + deadline_seconds
        pg_isready = self._postgres_bin("pg_isready")
        while time.monotonic() < deadline:
            result = self.runner.run((pg_isready,), environment=environment, check=False)
            if result.returncode == 0:
                return
            time.sleep(0.5)
        raise DeploymentError("PostgreSQL did not become ready on loopback.", exit_code=6)

    def _check_database_authentication(self, values: Mapping[str, str]) -> bool:
        result = self.runner.run(
            (self._postgres_bin("psql"), "--no-psqlrc", "--tuples-only", "--command", "SELECT 1"),
            environment=self._database_environment(values),
            check=False,
        )
        return result.returncode == 0 and result.stdout.strip() == "1"

    def _migration_environment(self, release: Path, values: Mapping[str, str]) -> dict[str, str]:
        environment = dict(os.environ)
        environment["DATABASE_URL"] = values["DATABASE_URL"]
        environment["PATH"] = f"{release / '.venv' / 'bin'}:{environment.get('PATH', '')}"
        return environment

    def _migration_revisions(
        self, release: Path, values: Mapping[str, str]
    ) -> tuple[set[str], set[str]]:
        alembic = release / ".venv" / "bin" / "alembic"
        environment = self._migration_environment(release, values)
        heads_output = self.runner.run((alembic, "heads"), cwd=release, environment=environment)
        current_output = self.runner.run((alembic, "current"), cwd=release, environment=environment)
        pattern = re.compile(r"\b[0-9]{8}_[0-9]{4}\b")
        return set(pattern.findall(heads_output.stdout)), set(
            pattern.findall(current_output.stdout)
        )

    def _validate_schema(self, release: Path, values: Mapping[str, str]) -> None:
        heads, current = self._migration_revisions(release, values)
        if not heads or heads != current:
            raise DeploymentError(
                "Database revision does not match the checked-out migration heads. "
                "Run an explicit update.",
                exit_code=EXIT_CONFIGURATION,
            )

    def _apply_migrations(self, release: Path, values: Mapping[str, str]) -> None:
        alembic = release / ".venv" / "bin" / "alembic"
        self.runner.run(
            (alembic, "upgrade", "head"),
            cwd=release,
            environment=self._migration_environment(release, values),
        )
        self._validate_schema(release, values)

    def _validate_checkout(self, release: Path) -> str:
        origin = self.runner.run(("/usr/bin/git", "remote", "get-url", "origin"), cwd=release)
        validate_origin(origin.stdout.strip())
        dirty = self.runner.run(("/usr/bin/git", "status", "--porcelain"), cwd=release)
        if dirty.stdout.strip():
            raise DeploymentError(
                "The deployed checkout has local changes; update refuses to overwrite them.",
                exit_code=EXIT_CONFLICT,
            )
        revision = self.runner.run(
            ("/usr/bin/git", "rev-parse", "HEAD"), cwd=release
        ).stdout.strip()
        if not REF_PATTERN.fullmatch(revision):
            raise DeploymentError("The checkout revision is invalid.", exit_code=4)
        return revision

    def _prepare_release(self, repository: str, revision: str) -> Path:
        if not REF_PATTERN.fullmatch(revision):
            raise DeploymentError(
                "--ref must be a full lowercase 40-character Git SHA.", exit_code=3
            )
        validate_origin(repository)
        release = self.paths.releases_root / revision
        if release.exists():
            if self._validate_checkout(release) != revision:
                raise DeploymentError(
                    "Existing release directory has the wrong revision.", exit_code=4
                )
            return release
        temporary = self.paths.releases_root / f".{revision}.candidate-{secrets.token_hex(4)}"
        try:
            self.runner.run(("/usr/bin/git", "init", "--quiet", temporary))
            self.runner.run(("/usr/bin/git", "remote", "add", "origin", repository), cwd=temporary)
            self.runner.run(
                ("/usr/bin/git", "fetch", "--depth=1", "origin", revision), cwd=temporary
            )
            fetched = self.runner.run(("/usr/bin/git", "rev-parse", "FETCH_HEAD"), cwd=temporary)
            if fetched.stdout.strip() != revision:
                raise DeploymentError(
                    "Fetched revision does not match the approved SHA.", exit_code=4
                )
            self.runner.run(("/usr/bin/git", "checkout", "--detach", "FETCH_HEAD"), cwd=temporary)
            if self._validate_checkout(temporary) != revision:
                raise DeploymentError(
                    "Prepared checkout revision changed unexpectedly.", exit_code=4
                )
            os.replace(temporary, release)
        except BaseException:
            remove_tree_within(temporary, self.paths.releases_root)
            raise
        return release

    def _build_release(self, release: Path) -> dict[str, Any]:
        venv = release / ".venv"
        constraint = release / "deploy" / "runpod" / "python-constraints.txt"
        pyproject_hash = sha256_file(release / "pyproject.toml")
        lock_hash = sha256_file(release / "frontend" / "package-lock.json")
        build_marker = venv / "runpod-build.json"
        if build_marker.is_file():
            previous = read_json(build_marker)
            if (
                previous.get("pyproject_sha256") == pyproject_hash
                and previous.get("package_lock_sha256") == lock_hash
                and (release / "frontend" / "dist" / "index.html").is_file()
                and (venv / "bin" / "video-app-api").is_file()
            ):
                return previous
        self.runner.run(("/usr/bin/python3", "-m", "venv", venv))
        pip = venv / "bin" / "python"
        self.runner.run(
            (
                pip,
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--constraint",
                constraint,
                "-e",
                ".",
                "alembic==1.19.0",
            ),
            cwd=release,
        )
        self.runner.run((pip, "-m", "pip", "check"), cwd=release)
        freeze = self.runner.run((pip, "-m", "pip", "freeze", "--all"), cwd=release)
        freeze_path = venv / "python-freeze.txt"
        atomic_write(freeze_path, freeze.stdout, mode=0o644)
        frontend = release / "frontend"
        self.runner.run(("/usr/bin/npm", "ci"), cwd=frontend)
        self.runner.run(("/usr/bin/npm", "run", "typecheck"), cwd=frontend)
        self.runner.run(("/usr/bin/npm", "run", "build"), cwd=frontend)
        audit = self.runner.run(
            ("/usr/bin/npm", "audit", "--json"), cwd=frontend, check=False, timeout=120
        )
        try:
            audit_payload = json.loads(audit.stdout)
        except json.JSONDecodeError:
            audit_payload = {}
        audit_metadata = (
            audit_payload.get("metadata", {}) if isinstance(audit_payload, dict) else {}
        )
        vulnerabilities = (
            audit_metadata.get("vulnerabilities", {}) if isinstance(audit_metadata, dict) else {}
        )
        python_version = self.runner.run((pip, "--version"), cwd=release)
        node_version = self.runner.run(("/usr/bin/node", "--version"), cwd=frontend)
        npm_version = self.runner.run(("/usr/bin/npm", "--version"), cwd=frontend)
        payload: dict[str, Any] = {
            "built_at": utc_now(),
            "pyproject_sha256": pyproject_hash,
            "package_lock_sha256": lock_hash,
            "python_environment_sha256": sha256_file(freeze_path),
            "python_tool": python_version.stdout.strip(),
            "node_version": node_version.stdout.strip(),
            "npm_version": npm_version.stdout.strip(),
            "npm_audit_exit_code": audit.returncode,
            "npm_audit_vulnerabilities": vulnerabilities,
        }
        atomic_json(build_marker, payload, mode=0o644)
        return payload

    def _activate_release(self, release: Path) -> None:
        temporary = self.paths.install_root / f".current-{secrets.token_hex(4)}"
        temporary.symlink_to(release, target_is_directory=True)
        os.replace(temporary, self.paths.current_root)

    def _postgres_bin_directory(self) -> Path:
        return self._postgres_bin("postgres").parent

    def _render_configs(self, postgres_port: int = 5432) -> None:
        release = self._current_release()
        values = parse_env_file(self.paths.env_file)
        configured_data = Path(values["VIDEO_APP_DATA_ROOT"])
        if (
            configured_data.is_symlink()
            or configured_data.resolve() != self.paths.application_data.resolve()
        ):
            raise DeploymentError(
                "VIDEO_APP_DATA_ROOT must match the deployment-managed data directory.", exit_code=4
            )
        max_upload = values.get("VIDEO_APP_MAX_UPLOAD_BYTES", "52428800")
        common = {
            "INSTALL_ROOT": str(self.paths.install_root),
            "CURRENT_ROOT": str(self.paths.current_root),
            "CONFIG_ROOT": str(self.paths.config_root),
            "STATE_ROOT": str(self.paths.state_root),
            "LOG_ROOT": str(self.paths.log_root),
            "RUN_ROOT": str(self.paths.run_root),
            "ENV_FILE": str(self.paths.env_file),
            "NGINX_CONFIG": str(self.paths.nginx_config),
            "SUPERVISOR_SOCKET": str(self.paths.supervisor_socket),
            "POSTGRES_BIN": str(self._postgres_bin("postgres")),
            "POSTGRES_DATA": str(self.paths.postgres_data),
            "POSTGRES_PORT": str(postgres_port),
            "POSTGRES_SOCKET_DIR": str(self.paths.postgres_socket_dir),
            "TAILSCALE_STATE": str(self.paths.tailscale_state),
            "TAILSCALE_SOCKET": str(self.paths.tailscale_socket),
            "TAILSCALE_CONFIG": str(self.paths.tailscale_config),
            "MAX_UPLOAD_BYTES": max_upload,
        }
        supervisor_template = (self.template_root / "supervisord.conf.template").read_text(
            encoding="utf-8"
        )
        nginx_template = (self.template_root / "nginx.conf.template").read_text(encoding="utf-8")
        atomic_write(
            self.paths.supervisor_config,
            render_template(supervisor_template, common),
            mode=0o640,
        )
        atomic_write(self.paths.nginx_config, render_template(nginx_template, common), mode=0o640)
        if not self.paths.tailscale_config.exists():
            atomic_json(
                self.paths.tailscale_config,
                {"version": "alpha0", "enabled": True, "locked": False},
                mode=0o600,
            )
        self.runner.run(("/usr/sbin/nginx", "-t", "-c", self.paths.nginx_config))
        self.runner.run(
            (
                release / ".venv" / "bin" / "python",
                "-c",
                _RUNTIME_CONFIG_CHECK,
                self.paths.env_file,
            ),
            cwd=release,
        )

    def _initialize_postgres(self) -> None:
        data = self.paths.postgres_data
        if data.exists() and any(data.iterdir()):
            raise DeploymentError(
                "PostgreSQL data already exists and was not initialized by this deployment.",
                exit_code=EXIT_CONFLICT,
            )
        candidate = self.paths.state_root / f".postgres-init-{secrets.token_hex(5)}"
        candidate.mkdir(mode=0o700)
        try:
            self.runner.run(("/usr/bin/chown", "postgres:postgres", candidate))
            self.runner.run(
                (
                    "/usr/sbin/runuser",
                    "-u",
                    "postgres",
                    "--",
                    self._postgres_bin("initdb"),
                    "-D",
                    candidate,
                    "--auth-local=peer",
                    "--auth-host=scram-sha-256",
                    "--encoding=UTF8",
                    "--locale=C.UTF-8",
                )
            )
            if data.exists():
                remove_tree_within(data, self.paths.state_root)
            os.replace(candidate, data)
        except BaseException:
            remove_tree_within(candidate, self.paths.state_root)
            raise

    def _validate_postgres_compatibility(self) -> None:
        version_file = self.paths.postgres_data / "PG_VERSION"
        if not version_file.is_file():
            raise DeploymentError("PostgreSQL data has no PG_VERSION marker.", exit_code=4)
        data_major = version_file.read_text(encoding="ascii").strip().split(".", 1)[0]
        binary = self.runner.run((self._postgres_bin("postgres"), "--version"))
        match = re.search(r"\b([0-9]+)(?:\.[0-9]+)?\b", binary.stdout)
        if match is None or match.group(1) != data_major:
            raise DeploymentError(
                "PostgreSQL data and executable major versions do not match; "
                "automatic upgrade is disabled.",
                exit_code=EXIT_CONFLICT,
            )

    def _ensure_application_database(self, password: str) -> None:
        if not self._application_role_exists():
            escaped = password.replace("'", "''")
            self._postgres_admin(
                f"CREATE ROLE {APP_ROLE} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                f"NOINHERIT PASSWORD '{escaped}';\n"
            )
        if not self._application_database_exists():
            self.runner.run(
                (
                    "/usr/sbin/runuser",
                    "-u",
                    "postgres",
                    "--",
                    self._postgres_bin("createdb"),
                    "--host",
                    self.paths.postgres_socket_dir,
                    "--owner",
                    APP_ROLE,
                    APP_DATABASE,
                )
            )

    def _package_versions(self) -> dict[str, str]:
        result = self.runner.run(
            (
                "/usr/bin/dpkg-query",
                "-W",
                "-f=${Package}=${Version}\\n",
                "nginx",
                "supervisor",
                "postgresql",
                "postgresql-client",
                "tailscale",
                "nodejs",
                "python3",
            ),
            check=False,
        )
        return dict(
            line.split("=", 1)
            for line in result.stdout.splitlines()
            if "=" in line and line.split("=", 1)[0]
        )

    def _listening_ports(self) -> dict[int, str]:
        result = self.runner.run(("/usr/bin/ss", "-H", "-ltnp"), check=False)
        if result.returncode != 0:
            raise DeploymentError("Cannot inspect local TCP listeners with ss.", exit_code=5)
        return parse_listening_ports(result.stdout)

    def _assert_managed_ports_available(self, states: Mapping[str, str]) -> None:
        listeners = self._listening_ports()
        conflicts = [
            f"{name} requires {port}/tcp ({listeners[port]})"
            for name, port in MANAGED_PORTS.items()
            if port in listeners and states.get(name) != "RUNNING"
        ]
        if conflicts:
            raise DeploymentError(
                "A required port is owned outside this deployment: " + "; ".join(conflicts),
                exit_code=EXIT_CONFLICT,
            )

    def _postgres_admin(self, sql: str, *, database: str = "postgres") -> CommandResult:
        return self.runner.run(
            (
                "/usr/sbin/runuser",
                "-u",
                "postgres",
                "--",
                self._postgres_bin("psql"),
                "--no-psqlrc",
                "--host",
                self.paths.postgres_socket_dir,
                "--dbname",
                database,
                "--tuples-only",
                "--no-align",
                "--set",
                "ON_ERROR_STOP=1",
            ),
            input_text=sql,
        )

    def _postgres_catalog_contains(self, sql: str) -> bool:
        return self._postgres_admin(sql).stdout.strip() == "1"

    def _application_role_exists(self) -> bool:
        return self._postgres_catalog_contains(
            f"SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}';\n"
        )

    def _application_database_exists(self) -> bool:
        return self._postgres_catalog_contains(
            f"SELECT 1 FROM pg_database WHERE datname = '{APP_DATABASE}';\n"
        )

    def _public_table_count(self, values: Mapping[str, str]) -> int:
        result = self.runner.run(
            (
                self._postgres_bin("psql"),
                "--no-psqlrc",
                "--tuples-only",
                "--no-align",
                "--command",
                "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';",
            ),
            environment=self._database_environment(values),
        )
        try:
            return int(result.stdout.strip())
        except ValueError as error:
            raise DeploymentError(
                "Could not inspect the application database.", exit_code=6
            ) from error

    def _database_size(self, values: Mapping[str, str]) -> int:
        result = self.runner.run(
            (
                self._postgres_bin("psql"),
                "--no-psqlrc",
                "--tuples-only",
                "--no-align",
                "--command",
                "SELECT pg_database_size(current_database());",
            ),
            environment=self._database_environment(values),
        )
        try:
            return int(result.stdout.strip())
        except ValueError as error:
            raise DeploymentError(
                "Could not measure the application database.", exit_code=7
            ) from error

    def _sample_record_counts(self, values: Mapping[str, str]) -> dict[str, int]:
        result = self.runner.run(
            (
                self._postgres_bin("psql"),
                "--no-psqlrc",
                "--tuples-only",
                "--no-align",
                "--command",
                "SELECT 'generation_jobs=' || count(*) FROM generation_jobs "
                "UNION ALL SELECT 'media_assets=' || count(*) FROM media_assets "
                "UNION ALL SELECT 'projects=' || count(*) FROM projects ORDER BY 1;",
            ),
            environment=self._database_environment(values),
        )
        counts: dict[str, int] = {}
        try:
            for line in result.stdout.splitlines():
                name, value = line.split("=", 1)
                counts[name] = int(value)
        except ValueError as error:
            raise DeploymentError("Could not sample application records.", exit_code=7) from error
        expected = {"generation_jobs", "media_assets", "projects"}
        if set(counts) != expected:
            raise DeploymentError("Application record sample is incomplete.", exit_code=7)
        return counts

    def _complete_installation(
        self,
        manifest: dict[str, Any],
        release: Path,
        values: Mapping[str, str],
        restore_archive: Path | None,
    ) -> None:
        version_file = self.paths.postgres_data / "PG_VERSION"
        if version_file.exists():
            self._validate_postgres_compatibility()
        else:
            self._initialize_postgres()
        self._render_configs()
        self._ensure_supervisor()
        self._assert_managed_ports_available(self._service_states())
        self._start_service("video-factory-postgres")
        self._wait_postgres(values)
        _, password, _, _ = parse_database_url(values["DATABASE_URL"])
        self._ensure_application_database(password)
        if not self._check_database_authentication(values):
            raise DeploymentError("Application database authentication failed.", exit_code=6)

        mode = manifest.get("initialization_mode")
        if mode == "restore":
            if restore_archive is None:
                raise DeploymentError(
                    "Interrupted restore installation requires the original --restore archive.",
                    exit_code=EXIT_CONFIGURATION,
                )
            if not restore_archive.is_absolute():
                raise DeploymentError("Restore archive path must be absolute.", exit_code=3)
            if restore_archive.is_symlink() or not restore_archive.is_file():
                raise DeploymentError("Restore archive must be a regular file.", exit_code=7)
            resolved_archive = restore_archive.resolve(strict=True)
            if sha256_file(resolved_archive) != manifest.get("restore_archive_sha256"):
                raise DeploymentError(
                    "Restore archive does not match the interrupted installation.", exit_code=7
                )
            if not bool(manifest.get("data_restored")):
                self.restore(resolved_archive, replace_existing=False, confirmation=None)
            else:
                self._validate_schema(release, values)
        elif mode == "empty":
            if restore_archive is not None:
                raise DeploymentError(
                    "Interrupted empty installation cannot be resumed as a restore.", exit_code=4
                )
            if self._public_table_count(values) == 0:
                self._apply_migrations(release, values)
            else:
                self._validate_schema(release, values)
        else:
            raise DeploymentError("Installation metadata has an invalid mode.", exit_code=3)

        manifest = self._deployment()
        manifest["install_state"] = "ready"
        manifest["data_restored"] = mode == "restore"
        manifest["initialized_empty_database"] = mode == "empty"
        manifest["updated_at"] = utc_now()
        atomic_json(self.paths.deployment_manifest, manifest, mode=0o640)
        self.start()
        print("Video Factory demo installation completed on EPHEMERAL storage.")
        print("No off-Pod backup exists until an operator exports and verifies one.")

    def install(
        self,
        *,
        repository: str,
        revision: str,
        accept_ephemeral: bool,
        initialize_empty_database: bool,
        restore_archive: Path | None,
        password_file: Path | None,
        owner_id: str,
    ) -> None:
        self._require_root()
        if not accept_ephemeral:
            raise DeploymentError(
                "Fresh installation requires --accept-ephemeral.", exit_code=EXIT_CONFIGURATION
            )
        if initialize_empty_database == (restore_archive is not None):
            raise DeploymentError(
                "Choose exactly one of --initialize-empty-database or --restore.",
                exit_code=EXIT_CONFIGURATION,
            )
        if restore_archive is not None and (
            not restore_archive.is_absolute()
            or restore_archive.is_symlink()
            or not restore_archive.is_file()
        ):
            raise DeploymentError(
                "Restore archive must be an absolute regular file.", exit_code=EXIT_BACKUP
            )
        with InstallationLock(self.paths.run_root / "install.lock"):
            self._ensure_directories()
            if self.paths.deployment_manifest.exists():
                deployed = self._deployment()
                if deployed.get("deployed_ref") != revision:
                    raise DeploymentError(
                        "An installation already exists; use runpodctl update --ref.", exit_code=4
                    )
                release = self._prepare_release(repository, revision)
                build = self._build_release(release)
                self._activate_release(release)
                values = parse_env_file(self.paths.env_file)
                state = deployed.get("install_state", "ready")
                if state == "initializing":
                    if password_file is not None:
                        raise DeploymentError(
                            "An interrupted installation preserves its existing database password.",
                            exit_code=4,
                        )
                    deployed["build"] = build
                    atomic_json(self.paths.deployment_manifest, deployed, mode=0o640)
                    self._complete_installation(deployed, release, values, restore_archive)
                    return
                if state != "ready":
                    raise DeploymentError(
                        "Installation metadata has an invalid state.", exit_code=3
                    )
                if restore_archive is not None or password_file is not None:
                    raise DeploymentError(
                        "Existing installs use runpodctl restore or rotate-db-password explicitly.",
                        exit_code=EXIT_CONFLICT,
                    )
                self._validate_postgres_compatibility()
                self._render_configs()
                print("Existing installation validated; configuration and database were preserved.")
                return
            if self.paths.env_file.exists() or (
                self.paths.postgres_data.exists() and any(self.paths.postgres_data.iterdir())
            ):
                raise DeploymentError(
                    "Unidentified configuration or database data exists; refusing initialization.",
                    exit_code=EXIT_CONFLICT,
                )
            release = self._prepare_release(repository, revision)
            build = self._build_release(release)
            self._activate_release(release)
            password = (
                read_private_secret(password_file, label="Database password")
                if password_file is not None
                else secrets.token_urlsafe(36)
            )
            values = demo_environment(self.paths, password=password, owner_id=owner_id)
            atomic_write(self.paths.env_file, serialize_environment(values), mode=0o600)
            manifest: dict[str, Any] = {
                "format": 1,
                "installation_id": secrets.token_hex(16),
                "repository": REPOSITORY_URL,
                "deployed_ref": revision,
                "install_state": "initializing",
                "initialization_mode": "empty" if initialize_empty_database else "restore",
                "restore_archive_sha256": (
                    sha256_file(restore_archive.resolve(strict=True))
                    if restore_archive is not None and restore_archive.is_absolute()
                    else None
                ),
                "installed_at": utc_now(),
                "updated_at": utc_now(),
                "storage_mode": "EPHEMERAL",
                "data_restored": False,
                "initialized_empty_database": initialize_empty_database,
                "pod_boot_integration": "NOT_CONFIGURED",
                "postgres_bin_dir": str(self._postgres_bin_directory()),
                "system_packages": self._package_versions(),
                "build": build,
            }
            if restore_archive is not None and manifest["restore_archive_sha256"] is None:
                raise DeploymentError("Restore archive path must be absolute.", exit_code=3)
            atomic_json(self.paths.deployment_manifest, manifest, mode=0o640)
            self._complete_installation(manifest, release, values, restore_archive)

    def start(self) -> None:
        self._require_root()
        with InstallationLock(self.paths.run_root / "operation.lock"):
            release = self._current_release()
            self._validate_checkout(release)
            values = parse_env_file(self.paths.env_file)
            self._render_configs()
            self._validate_postgres_compatibility()
            self._ensure_supervisor()
            self._assert_managed_ports_available(self._service_states())
            self._start_service("video-factory-postgres")
            self._wait_postgres(values)
            if not self._check_database_authentication(values):
                raise DeploymentError("Application database authentication failed.", exit_code=6)
            self._validate_schema(release, values)
            self._start_service("video-factory-api")
            self._wait_http("http://127.0.0.1:8000/api/v1/health")
            self._start_service("video-factory-nginx")
            self._wait_http("http://127.0.0.1:5173/")
            self._wait_http("http://127.0.0.1:5173/api/v1/health")
            self._start_service("video-factory-worker")
            self._start_service("video-factory-tailscaled")
            self._wait_tailscale_daemon()
            if self._tailscale_authorized() and not self._tailscale_serve_status()["configured"]:
                self._configure_tailscale_serve()
            worker_count = sum(
                state == "RUNNING"
                for name, state in self._service_states().items()
                if name == "video-factory-worker"
            )
            if worker_count != 1:
                raise DeploymentError("Expected exactly one managed worker.", exit_code=6)
            print("Video Factory managed services are running.")

    def stop(self) -> None:
        self._require_root()
        with InstallationLock(self.paths.run_root / "operation.lock"):
            for name in reversed(SERVICE_NAMES):
                self._stop_service(name)
            if self.paths.supervisor_socket.exists():
                self._supervisorctl("shutdown", check=False)
            print("Video Factory managed services stopped; ComfyUI and Jupyter were not touched.")

    def restart(self) -> None:
        self.stop()
        self.start()

    def _wait_tailscale_daemon(self, *, deadline_seconds: int = 20) -> None:
        deadline = time.monotonic() + deadline_seconds
        while time.monotonic() < deadline:
            result = self.runner.run(
                ("/usr/bin/tailscale", "--socket", self.paths.tailscale_socket, "status", "--json"),
                check=False,
            )
            try:
                payload = json.loads(result.stdout)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict) and isinstance(payload.get("BackendState"), str):
                return
            time.sleep(0.5)
        raise DeploymentError("tailscaled is not responding on its private socket.", exit_code=6)

    def _tailscale_status(self) -> dict[str, Any]:
        try:
            result = self.runner.run(
                (
                    "/usr/bin/tailscale",
                    "--socket",
                    self.paths.tailscale_socket,
                    "status",
                    "--json",
                ),
                check=False,
            )
        except DeploymentError:
            return {"daemon": "unavailable", "authorization": "unknown", "url": None}
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            state = "unavailable" if result.returncode != 0 else "invalid_response"
            return {"daemon": state, "authorization": "unknown", "url": None}
        if not isinstance(payload, dict):
            return {"daemon": "invalid_response", "authorization": "unknown", "url": None}
        backend_state = payload.get("BackendState")
        self_data = payload.get("Self") if isinstance(payload.get("Self"), dict) else {}
        dns_name = self_data.get("DNSName") if isinstance(self_data, dict) else None
        hostname = dns_name.rstrip(".") if isinstance(dns_name, str) else None
        normalized_backend_state = backend_state if isinstance(backend_state, str) else "unknown"
        authorization = {
            "Running": "authorized",
            "NeedsLogin": "login_required",
            "NeedsMachineAuth": "approval_required",
        }.get(normalized_backend_state, "not_ready")
        return {
            "daemon": "ready",
            "authorization": authorization,
            "backend_state": normalized_backend_state,
            "url": f"https://{hostname}/" if hostname else None,
        }

    def _tailscale_authorized(self) -> bool:
        return self._tailscale_status().get("authorization") == "authorized"

    def _tailscale_serve_status(self) -> dict[str, Any]:
        if not self._tailscale_authorized():
            return {"configured": False, "state": "authorization_required"}
        result = self.runner.run(
            (
                "/usr/bin/tailscale",
                "--socket",
                self.paths.tailscale_socket,
                "serve",
                "status",
                "--json",
            ),
            check=False,
        )
        if result.returncode != 0:
            return {"configured": False, "state": "status_unavailable"}
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"configured": False, "state": "invalid_response"}
        configured = isinstance(payload, dict) and bool(payload)
        return {"configured": configured, "state": "configured" if configured else "empty"}

    def _configure_tailscale_serve(self) -> None:
        result = self.runner.run(
            (
                "/usr/bin/tailscale",
                "--socket",
                self.paths.tailscale_socket,
                "serve",
                "--bg",
                "--https=443",
                "http://127.0.0.1:5173",
            ),
            check=False,
            timeout=60,
        )
        if result.returncode != 0:
            raise DeploymentError("Tailscale Serve HTTPS configuration failed.", exit_code=8)

    def tailscale_login(self, auth_key_file: Path | None) -> None:
        self._require_root()
        self._ensure_supervisor()
        self._start_service("video-factory-tailscaled")
        self._wait_tailscale_daemon()
        if self._tailscale_authorized():
            if not self._tailscale_serve_status()["configured"]:
                self._configure_tailscale_serve()
            print(self._tailscale_status().get("url") or "Tailscale is authorized.")
            return
        if auth_key_file is None:
            result = self.runner.run(
                (
                    "/usr/bin/tailscale",
                    "--socket",
                    self.paths.tailscale_socket,
                    "login",
                    "--timeout=5m",
                ),
                capture=False,
                check=False,
            )
            if result.returncode != 0:
                raise DeploymentError("Interactive Tailscale login was not completed.", exit_code=8)
        else:
            if not auth_key_file.is_absolute():
                raise DeploymentError("Tailscale auth-key path must be absolute.", exit_code=3)
            resolved = auth_key_file.resolve(strict=True)
            mode = stat.S_IMODE(resolved.stat().st_mode)
            if not resolved.is_file() or resolved.is_symlink() or mode & 0o077:
                raise DeploymentError(
                    "The Tailscale auth-key file must be a private regular file (mode 0600).",
                    exit_code=3,
                )
            atomic_json(
                self.paths.tailscale_config,
                {
                    "version": "alpha0",
                    "enabled": True,
                    "locked": False,
                    "authKey": f"file:{resolved}",
                },
                mode=0o600,
            )
            self._supervisorctl("restart", "video-factory-tailscaled")
            self._wait_tailscale_daemon(deadline_seconds=60)
            if not self._tailscale_authorized():
                raise DeploymentError(
                    "Tailscale auth key was rejected or needs approval.", exit_code=8
                )
            atomic_json(
                self.paths.tailscale_config,
                {"version": "alpha0", "enabled": True, "locked": False},
                mode=0o600,
            )
            self._supervisorctl("restart", "video-factory-tailscaled")
            self._wait_tailscale_daemon()
        self._configure_tailscale_serve()
        status = self._tailscale_status()
        print(status.get("url") or "Tailscale authorized; hostname is not yet available.")

    def _http_status(
        self,
        url: str,
        *,
        expected_text: Sequence[str] = (),
        expected_json: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                body = response.read(HTTP_PROBE_BODY_LIMIT + 1)
                status = int(response.status)
                content_valid = len(body) <= HTTP_PROBE_BODY_LIMIT
                if content_valid and expected_text:
                    decoded = body.decode("utf-8", errors="replace")
                    content_valid = all(marker in decoded for marker in expected_text)
                if content_valid and expected_json is not None:
                    try:
                        content_valid = json.loads(body) == expected_json
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        content_valid = False
                healthy = status == 200 and content_valid
                return {
                    "reachable": True,
                    "healthy": healthy,
                    "status": status,
                    "content_valid": content_valid,
                    "failure": None
                    if healthy
                    else ("unexpected_status" if status != 200 else "unexpected_content"),
                    "latency_ms": round((time.monotonic() - started) * 1000),
                }
        except urllib.error.HTTPError as error:
            return {
                "reachable": True,
                "healthy": False,
                "status": error.code,
                "content_valid": False,
                "failure": "unexpected_status",
                "latency_ms": round((time.monotonic() - started) * 1000),
            }
        except (OSError, urllib.error.URLError) as error:
            return {
                "reachable": False,
                "healthy": False,
                "status": None,
                "content_valid": False,
                "failure": "transport_error",
                "error": type(error).__name__,
            }

    def _frontend_http_status(self) -> dict[str, Any]:
        return self._http_status("http://127.0.0.1:5173/", expected_text=FRONTEND_HTTP_MARKERS)

    def _api_http_status(self, url: str) -> dict[str, Any]:
        return self._http_status(url, expected_json=API_HEALTH_RESPONSE)

    def _schema_status(self, release: Path, values: Mapping[str, str]) -> dict[str, Any]:
        try:
            heads, current = self._migration_revisions(release, values)
        except DeploymentError:
            return {"state": "unavailable", "heads": [], "current": []}
        return {
            "state": "current" if heads and heads == current else "mismatch",
            "heads": sorted(heads),
            "current": sorted(current),
        }

    def status_payload(self) -> dict[str, Any]:
        try:
            deployment = self._deployment() if self.paths.deployment_manifest.exists() else {}
        except DeploymentError:
            deployment = {"metadata_state": "invalid"}
        release: Path | None = None
        source_state = "not_installed"
        deployed_ref = deployment.get("deployed_ref")
        try:
            release = self._current_release()
            actual_ref = self._validate_checkout(release)
            source_state = "clean" if actual_ref == deployed_ref else "revision_mismatch"
        except DeploymentError:
            actual_ref = None
        try:
            values = parse_env_file(self.paths.env_file)
            configuration_state = "valid"
            backend = values.get("VIDEO_APP_BACKEND", "unknown")
        except DeploymentError:
            values = {}
            configuration_state = "invalid"
            backend = "unknown"
        states = self._service_states()
        try:
            database_auth = bool(values) and self._check_database_authentication(values)
        except DeploymentError:
            database_auth = False
        schema = (
            self._schema_status(release, values)
            if release is not None and database_auth
            else {"state": "unavailable", "heads": [], "current": []}
        )
        disk = shutil.disk_usage(self.paths.state_root) if self.paths.state_root.exists() else None
        tailscale = self._tailscale_status()
        tailscale["serve"] = self._tailscale_serve_status()
        try:
            smoke = read_json(self.paths.smoke_report) if self.paths.smoke_report.exists() else None
        except DeploymentError:
            smoke = {"state": "invalid"}
        latest_backup = deployment.get("last_backup")
        payload: dict[str, Any] = {
            "installed": bool(deployment),
            "installation_id": deployment.get("installation_id"),
            "storage": {
                "mode": deployment.get("storage_mode", "UNKNOWN"),
                "warning": "Pod-local state is ephemeral; keep a verified off-Pod backup.",
                "off_pod_backup": "NOT_VERIFIED",
            },
            "source": {
                "state": source_state,
                "deployed_ref": deployed_ref,
                "actual_ref": actual_ref,
            },
            "configuration": configuration_state,
            "services": states,
            "worker_process_count": 1 if states.get("video-factory-worker") == "RUNNING" else 0,
            "database": {
                "readiness": "ready" if database_auth else "failed_or_unavailable",
                "authentication": "ok" if database_auth else "failed_or_unavailable",
                "schema": schema,
                "bind": "127.0.0.1:5432",
            },
            "http": {
                "frontend": self._frontend_http_status(),
                "api": self._api_http_status("http://127.0.0.1:5173/api/v1/health"),
                "api_direct": self._api_http_status("http://127.0.0.1:8000/api/v1/health"),
                "bind": "127.0.0.1:5173",
            },
            "tailscale": tailscale,
            "external_tls": (
                "configured_private_serve_unverified_here"
                if tailscale["serve"].get("configured")
                else "not_configured"
            ),
            "runtime": {
                "backend": backend,
                "demo_mode": backend == "fake",
                "gpu_qualification": (
                    "NOT_APPLICABLE_FAKE"
                    if backend == "fake"
                    else "REQUIRES_ADAPTER_QUALIFICATION_CHECK"
                ),
                "pod_boot_integration": deployment.get("pod_boot_integration", "NOT_CONFIGURED"),
            },
            "backup": {
                "latest": latest_backup,
                "note": "A local path does not prove an off-Pod copy exists.",
            },
            "last_smoke_test": smoke,
            "npm_audit_exit_code": (
                deployment.get("build", {}).get("npm_audit_exit_code")
                if isinstance(deployment.get("build"), dict)
                else None
            ),
            "npm_audit_vulnerabilities": (
                deployment.get("build", {}).get("npm_audit_vulnerabilities")
                if isinstance(deployment.get("build"), dict)
                else None
            ),
        }
        if disk is not None:
            payload["storage"]["bytes_total"] = disk.total
            payload["storage"]["bytes_free"] = disk.free
        return payload

    def status(self, *, output_json: bool) -> None:
        payload = self.status_payload()
        if output_json:
            print(json.dumps(payload, sort_keys=True, indent=2))
            return
        print(f"installed: {payload['installed']}")
        print(f"storage: {payload['storage']['mode']} (off-Pod backup NOT VERIFIED)")
        print(f"source: {payload['source']['state']} @ {payload['source']['deployed_ref']}")
        print(f"configuration: {payload['configuration']}")
        for name, state in payload["services"].items():
            print(f"service {name}: {state}")
        print(f"worker process count: {payload['worker_process_count']}")
        print(f"database authentication: {payload['database']['authentication']}")
        print(f"database schema: {payload['database']['schema']['state']}")
        print(f"frontend: {payload['http']['frontend']['healthy']}")
        print(f"api: {payload['http']['api']['healthy']}")
        print(f"tailscale authorization: {payload['tailscale']['authorization']}")
        print(f"private URL: {payload['tailscale'].get('url') or 'unavailable'}")
        print(f"backend: {payload['runtime']['backend']} (demo={payload['runtime']['demo_mode']})")
        print(f"Pod boot integration: {payload['runtime']['pod_boot_integration']}")

    def doctor_payload(self) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []

        def add(name: str, state: str, detail: str) -> None:
            checks.append({"name": name, "state": state, "detail": detail})

        for executable in (
            "git",
            "nginx",
            "supervisord",
            "supervisorctl",
            "tailscale",
            "tailscaled",
            "ss",
            "npm",
        ):
            found = shutil.which(executable)
            add(f"executable:{executable}", "pass" if found else "fail", found or "missing")
        try:
            values = parse_env_file(self.paths.env_file)
            add("configuration", "pass", "strict environment validation passed")
        except DeploymentError as error:
            values = {}
            add("configuration", "fail", str(error))
        try:
            release = self._current_release()
            revision = self._validate_checkout(release)
            add("source", "pass", revision)
        except DeploymentError as error:
            release = None
            add("source", "fail", str(error))
        states = self._service_states()
        add(
            "services",
            "pass" if all(value == "RUNNING" for value in states.values()) else "fail",
            ", ".join(f"{key}={value}" for key, value in states.items()),
        )
        worker_count = 1 if states.get("video-factory-worker") == "RUNNING" else 0
        add(
            "worker-process-count",
            "pass" if worker_count == 1 else "fail",
            str(worker_count),
        )
        if values:
            try:
                authenticated = self._check_database_authentication(values)
            except DeploymentError:
                authenticated = False
            add(
                "database-authentication",
                "pass" if authenticated else "fail",
                "application role accepted" if authenticated else "application role rejected",
            )
            if authenticated and release is not None:
                schema = self._schema_status(release, values)
                add(
                    "database-schema",
                    "pass" if schema["state"] == "current" else "fail",
                    schema["state"],
                )
        try:
            listeners = self._listening_ports()
            unexpected = [
                f"{port}={listeners[port]}"
                for name, port in MANAGED_PORTS.items()
                if port in listeners and states.get(name) != "RUNNING"
            ]
        except DeploymentError as error:
            unexpected = [str(error)]
        add(
            "port-ownership",
            "pass" if not unexpected else "fail",
            "managed or unused" if not unexpected else "; ".join(unexpected),
        )
        tailscale = self._tailscale_status()
        add(
            "tailscale-daemon",
            "pass" if tailscale["daemon"] == "ready" else "fail",
            tailscale["daemon"],
        )
        add(
            "tailscale-authorization",
            "pass" if tailscale["authorization"] == "authorized" else "warn",
            tailscale["authorization"],
        )
        serve = self._tailscale_serve_status()
        add(
            "tailscale-serve",
            "pass" if serve["configured"] else "warn",
            serve["state"],
        )
        add("external-peer", "not_verified", "requires a second authorized tailnet device")
        add("magic-dns", "not_verified", "userspace daemon cannot prove external DNS here")
        add("external-tcp-443", "not_verified", "test from Windows after authorization")
        add("external-tls", "not_verified", "a local TCP check is not TLS verification")
        add("vite-host-policy", "not_applicable", "production serves a built Nginx bundle")
        app_http = self._frontend_http_status()
        api_http = self._api_http_status("http://127.0.0.1:5173/api/v1/health")
        add(
            "frontend-http",
            "pass" if app_http["healthy"] else "fail",
            f"status={app_http.get('status')} content_valid={app_http['content_valid']}",
        )
        add(
            "api-http",
            "pass" if api_http["healthy"] else "fail",
            f"status={api_http.get('status')} content_valid={api_http['content_valid']}",
        )
        return {
            "checked_at": utc_now(),
            "healthy": not any(check["state"] == "fail" for check in checks),
            "checks": checks,
        }

    def doctor(self, *, output_json: bool) -> None:
        payload = self.doctor_payload()
        if output_json:
            print(json.dumps(payload, sort_keys=True, indent=2))
        else:
            for check in payload["checks"]:
                print(f"{check['state'].upper():4} {check['name']}: {check['detail']}")
        if not payload["healthy"]:
            raise DeploymentError("One or more deployment checks failed.", exit_code=EXIT_SERVICE)

    def logs(self, *, service: str | None, lines: int) -> None:
        if lines < 1 or lines > 10_000:
            raise DeploymentError("--lines must be between 1 and 10000.", exit_code=3)
        names = {
            "supervisor": "supervisord.log",
            "postgres": "postgres.log",
            "api": "api.log",
            "worker": "worker.log",
            "nginx": "nginx-supervisor.log",
            "nginx-error": "nginx-error.log",
            "tailscale": "tailscaled.log",
        }
        selected = names if service is None else {service: names[service]}
        secret_values: list[str] = []
        with contextlib.suppress(DeploymentError):
            values = parse_env_file(self.paths.env_file)
            secret_values.extend(values.values())
            _, password, _, _ = parse_database_url(values["DATABASE_URL"])
            secret_values.append(password)
        for label, filename in selected.items():
            path = self.paths.log_root / filename
            print(f"== {label} ==")
            if not path.is_file() or path.is_symlink():
                print("log unavailable")
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]
            except OSError:
                print("log unavailable")
                continue
            print(redact_text("\n".join(content), secret_values))

    def _json_request(
        self,
        url: str,
        *,
        method: str = "GET",
        payload: Mapping[str, Any] | None = None,
        timeout: float = 5,
    ) -> tuple[int, dict[str, Any]]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            method=method,
            headers={"Content-Type": "application/json"} if body is not None else {},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                decoded = json.loads(response.read().decode("utf-8"))
                if not isinstance(decoded, dict):
                    raise DeploymentError("Smoke-test API response was not an object.", exit_code=6)
                return response.status, decoded
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
            raise DeploymentError(
                "Smoke-test API request failed.", exit_code=EXIT_SERVICE
            ) from error

    def smoke_test(self, *, deadline_seconds: int) -> None:
        started = time.monotonic()
        values = parse_env_file(self.paths.env_file)
        if values.get("VIDEO_APP_BACKEND") != "fake":
            raise DeploymentError(
                "Routine smoke-test is restricted to VIDEO_APP_BACKEND=fake; "
                "GPU inference is separate.",
                exit_code=EXIT_CONFIGURATION,
            )
        self._wait_http("http://127.0.0.1:5173/")
        self._wait_http("http://127.0.0.1:5173/api/v1/health")
        status, job = self._json_request(
            "http://127.0.0.1:5173/api/v1/jobs",
            method="POST",
            payload={
                "mode": "text_to_video",
                "prompt": "RunPod deployment smoke test",
                "model": "wan21-t2v",
                "width": 832,
                "height": 480,
                "frame_count": 81,
                "seed": 20260821,
            },
        )
        job_id = job.get("id")
        if status != 202 or not isinstance(job_id, str):
            raise DeploymentError("Smoke-test job was not accepted.", exit_code=6)
        deadline = time.monotonic() + deadline_seconds
        terminal: dict[str, Any] = job
        while time.monotonic() < deadline:
            _, terminal = self._json_request(f"http://127.0.0.1:5173/api/v1/jobs/{job_id}")
            if terminal.get("status") in {"succeeded", "failed", "cancelled"}:
                break
            time.sleep(0.5)
        if terminal.get("status") != "succeeded":
            raise DeploymentError(
                f"Smoke-test job did not succeed (state={terminal.get('status')}).", exit_code=6
            )
        output_request = urllib.request.Request(
            f"http://127.0.0.1:5173/api/v1/jobs/{job_id}/output",
            headers={"Range": "bytes=0-15"},
        )
        try:
            with urllib.request.urlopen(output_request, timeout=5) as response:
                output = response.read(16)
                output_status = response.status
                output_type = response.headers.get_content_type()
        except (OSError, urllib.error.URLError) as error:
            raise DeploymentError("Smoke-test output retrieval failed.", exit_code=6) from error
        if (
            output_status not in {200, 206}
            or output_type != "video/mp4"
            or len(output) < 8
            or output[4:8] != b"ftyp"
        ):
            raise DeploymentError("Smoke-test output was empty or invalid.", exit_code=6)
        report = {
            "checked_at": utc_now(),
            "job_id": job_id,
            "job_status": terminal["status"],
            "output_http_status": output_status,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "backend": "fake",
            "real_ai_video_generated": False,
        }
        atomic_json(self.paths.smoke_report, report, mode=0o640)
        print(json.dumps(report, sort_keys=True, indent=2))

    def _extract_backup(self, archive: Path, destination: Path) -> dict[str, Any]:
        resolved = archive.resolve(strict=True)
        if not resolved.is_file() or resolved.is_symlink():
            raise DeploymentError("Backup must be a regular archive file.", exit_code=7)
        try:
            with tarfile.open(resolved, "r:*") as source:
                members = ensure_safe_archive_members(source.getmembers())
                uncompressed_bytes = sum(member.size for member in members if member.isfile())
                if len(members) > 1_000_000:
                    raise DeploymentError("Backup contains too many entries.", exit_code=7)
                if uncompressed_bytes > shutil.disk_usage(destination.parent).free:
                    raise DeploymentError("Backup exceeds available restore space.", exit_code=7)
                names = {member.name for member in members}
                if "manifest.json" not in names or "database.dump" not in names:
                    raise DeploymentError("Backup is missing required entries.", exit_code=7)
                for member in members:
                    target = destination / member.name
                    if member.isdir():
                        target.mkdir(parents=True, exist_ok=True)
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    extracted = source.extractfile(member)
                    if extracted is None:
                        raise DeploymentError("Backup entry could not be read.", exit_code=7)
                    with target.open("xb") as output:
                        shutil.copyfileobj(extracted, output)
                    os.chmod(target, 0o600)
        except (tarfile.TarError, OSError) as error:
            raise DeploymentError("Backup archive cannot be read safely.", exit_code=7) from error
        metadata = read_json(destination / "manifest.json")
        if metadata.get("format") != 1:
            raise DeploymentError("Unsupported backup format.", exit_code=7)
        expected_dump = metadata.get("database_sha256")
        if (
            not isinstance(expected_dump, str)
            or sha256_file(destination / "database.dump") != expected_dump
        ):
            raise DeploymentError("Backup database checksum does not match.", exit_code=7)
        expected_data = metadata.get("application_data_sha256")
        if not isinstance(expected_data, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in expected_data.items()
        ):
            raise DeploymentError("Backup data checksum manifest is invalid.", exit_code=7)
        verify_tree_checksums(destination / "data", expected_data)
        return metadata

    def backup(self, output: Path) -> Path:
        self._require_root()
        if not output.is_absolute():
            raise DeploymentError("Backup output must be an absolute path.", exit_code=3)
        if output.exists():
            raise DeploymentError("Backup output already exists; refusing overwrite.", exit_code=4)
        output.parent.mkdir(parents=True, exist_ok=True)
        deployment = self._deployment()
        release = self._current_release()
        values = parse_env_file(self.paths.env_file)
        self._ensure_supervisor()
        self._start_service("video-factory-postgres")
        self._wait_postgres(values)
        self._validate_schema(release, values)
        artifact_root = self.paths.application_data / "artifacts"
        required_space = (
            tree_size(artifact_root) * 2 + self._database_size(values) * 2 + 512 * 1024 * 1024
        )
        if shutil.disk_usage(self.paths.state_root).free < required_space:
            raise DeploymentError(
                "Insufficient staging space for a consistent media backup.", exit_code=7
            )
        if shutil.disk_usage(output.parent).free < required_space:
            raise DeploymentError("Insufficient space at the backup destination.", exit_code=7)
        states_before = self._service_states()
        with InstallationLock(self.paths.run_root / "backup.lock"):
            self._stop_service("video-factory-worker")
            self._stop_service("video-factory-api")
            try:
                with tempfile.TemporaryDirectory(
                    prefix=".backup-", dir=self.paths.state_root
                ) as name:
                    staging = Path(name)
                    dump_path = staging / "database.dump"
                    self.runner.run(
                        (
                            self._postgres_bin("pg_dump"),
                            "--format=custom",
                            "--no-owner",
                            "--no-privileges",
                            f"--file={dump_path}",
                        ),
                        environment=self._database_environment(values),
                        timeout=600,
                    )
                    staged_data = staging / "data"
                    staged_data.mkdir()
                    source_checksums = {
                        f"artifacts/{name}": digest
                        for name, digest in tree_checksums(artifact_root).items()
                    }
                    if artifact_root.exists():
                        shutil.copytree(
                            artifact_root,
                            staged_data / "artifacts",
                            symlinks=False,
                            dirs_exist_ok=False,
                        )
                    verify_tree_checksums(staged_data, source_checksums)
                    heads, current = self._migration_revisions(release, values)
                    pg_version = self.runner.run((self._postgres_bin("pg_dump"), "--version"))
                    version_match = re.search(r"\b([0-9]+)(?:\.[0-9]+)?\b", pg_version.stdout)
                    metadata: dict[str, Any] = {
                        "format": 1,
                        "created_at": utc_now(),
                        "installation_id": deployment.get("installation_id"),
                        "repository": deployment.get("repository"),
                        "deployed_ref": deployment.get("deployed_ref"),
                        "migration_heads": sorted(heads),
                        "migration_current": sorted(current),
                        "postgres_major": version_match.group(1) if version_match else None,
                        "database_sha256": sha256_file(dump_path),
                        "sample_record_counts": self._sample_record_counts(values),
                        "application_data_sha256": source_checksums,
                        "sample_media": next(iter(sorted(source_checksums)), None),
                        "excludes": ["Tailscale identity", "database credentials", "logs"],
                    }
                    atomic_json(staging / "manifest.json", metadata, mode=0o600)
                    partial = output.parent / f".{output.name}.{secrets.token_hex(4)}.partial"
                    try:
                        with tarfile.open(partial, "w:gz") as archive:
                            archive.add(
                                staging / "manifest.json", arcname="manifest.json", recursive=False
                            )
                            archive.add(
                                staging / "database.dump", arcname="database.dump", recursive=False
                            )
                            archive.add(staging / "data", arcname="data", recursive=True)
                        with tempfile.TemporaryDirectory(
                            prefix=".verify-", dir=self.paths.state_root
                        ) as verify_name:
                            self._extract_backup(partial, Path(verify_name))
                        os.replace(partial, output)
                        os.chmod(output, 0o600)
                    finally:
                        partial.unlink(missing_ok=True)
            finally:
                if states_before.get("video-factory-api") == "RUNNING":
                    self._start_service("video-factory-api")
                    self._wait_http("http://127.0.0.1:8000/api/v1/health")
                if states_before.get("video-factory-worker") == "RUNNING":
                    self._start_service("video-factory-worker")
        deployment["last_backup"] = {
            "created_at": metadata["created_at"],
            "path": str(output),
            "sha256": sha256_file(output),
            "off_pod_copy": "NOT_VERIFIED",
            "protection": "LOCAL ONLY — NOT PROTECTED FROM CONTAINER LOSS",
        }
        deployment["updated_at"] = utc_now()
        atomic_json(self.paths.deployment_manifest, deployment, mode=0o640)
        print(f"Verified backup created: {output}")
        print(f"SHA-256: {deployment['last_backup']['sha256']}")
        print(
            "Copy it off the Pod and verify that copy; this command cannot prove "
            "external durability."
        )
        return output

    def _create_restore_database(self, database: str) -> None:
        self.runner.run(
            (
                "/usr/sbin/runuser",
                "-u",
                "postgres",
                "--",
                self._postgres_bin("createdb"),
                "--host",
                self.paths.postgres_socket_dir,
                "--owner",
                APP_ROLE,
                database,
            )
        )

    def _drop_database(self, database: str) -> None:
        self._postgres_admin(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = '{database}' AND pid <> pg_backend_pid();\n"
            f'DROP DATABASE IF EXISTS "{database}";\n'
        )

    def restore(
        self,
        archive: Path,
        *,
        replace_existing: bool,
        confirmation: str | None,
    ) -> None:
        self._require_root()
        if not archive.is_absolute():
            raise DeploymentError("Restore archive path must be absolute.", exit_code=3)
        deployment = self._deployment()
        expected_confirmation = f"RESTORE-{deployment.get('installation_id')}"
        if replace_existing and confirmation != expected_confirmation:
            raise DeploymentError(
                f"Replacement restore requires --confirm {expected_confirmation}.", exit_code=3
            )
        release = self._current_release()
        values = parse_env_file(self.paths.env_file)
        self._ensure_supervisor()
        self._start_service("video-factory-postgres")
        self._wait_postgres(values)
        if not replace_existing and self._public_table_count(values) != 0:
            raise DeploymentError(
                "The application database is not empty; use explicit replacement confirmation.",
                exit_code=EXIT_CONFLICT,
            )
        with InstallationLock(self.paths.run_root / "restore.lock"):
            staging = Path(tempfile.mkdtemp(prefix=".restore-", dir=self.paths.state_root))
            restore_database = f"video_factory_restore_{secrets.token_hex(5)}"
            previous_database = f"video_factory_previous_{secrets.token_hex(5)}"
            previous_data = self.paths.state_root / f".data-previous-{secrets.token_hex(5)}"
            original_database_renamed = False
            database_swapped = False
            restore_committed = False
            try:
                metadata = self._extract_backup(archive, staging)
                data_major = (
                    (self.paths.postgres_data / "PG_VERSION")
                    .read_text(encoding="ascii")
                    .strip()
                    .split(".", 1)[0]
                )
                if metadata.get("postgres_major") != data_major:
                    raise DeploymentError(
                        "Backup PostgreSQL major version is incompatible with this installation.",
                        exit_code=EXIT_BACKUP,
                    )
                self._create_restore_database(restore_database)
                restore_values = dict(values)
                restore_values["DATABASE_URL"] = database_url_with_name(
                    values["DATABASE_URL"], restore_database
                )
                self.runner.run(
                    (
                        self._postgres_bin("pg_restore"),
                        "--exit-on-error",
                        "--no-owner",
                        "--no-privileges",
                        f"--dbname={restore_database}",
                        staging / "database.dump",
                    ),
                    environment=self._database_environment(restore_values),
                    timeout=1200,
                )
                self._validate_schema(release, restore_values)
                expected_counts = metadata.get("sample_record_counts")
                if (
                    not isinstance(expected_counts, dict)
                    or self._sample_record_counts(restore_values) != expected_counts
                ):
                    raise DeploymentError(
                        "Restored application record sample does not match the backup.",
                        exit_code=EXIT_BACKUP,
                    )
                self._stop_service("video-factory-worker")
                self._stop_service("video-factory-api")
                self._postgres_admin(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    f"WHERE datname IN ('{APP_DATABASE}', '{restore_database}') "
                    "AND pid <> pg_backend_pid();\n"
                )
                self._postgres_admin(
                    f'ALTER DATABASE "{APP_DATABASE}" RENAME TO "{previous_database}";\n'
                )
                original_database_renamed = True
                self._postgres_admin(
                    f'ALTER DATABASE "{restore_database}" RENAME TO "{APP_DATABASE}";\n'
                )
                database_swapped = True
                if self.paths.application_data.exists():
                    os.replace(self.paths.application_data, previous_data)
                os.replace(staging / "data", self.paths.application_data)
                self.start()
                deployment["last_restore"] = {
                    "restored_at": utc_now(),
                    "archive": str(archive.resolve()),
                    "backup_created_at": metadata.get("created_at"),
                    "backup_ref": metadata.get("deployed_ref"),
                }
                deployment["data_restored"] = True
                deployment["updated_at"] = utc_now()
                atomic_json(self.paths.deployment_manifest, deployment, mode=0o640)
                restore_committed = True
                remove_tree_within(previous_data, self.paths.state_root)
                self._drop_database(previous_database)
                print("Backup restored and validated; previous database and data were retired.")
            except BaseException:
                if original_database_renamed and not restore_committed:
                    self._stop_service("video-factory-worker")
                    self._stop_service("video-factory-api")
                    self._postgres_admin(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        f"WHERE datname IN ('{APP_DATABASE}', '{previous_database}') "
                        "AND pid <> pg_backend_pid();\n"
                    )
                    if database_swapped:
                        self._postgres_admin(
                            f'ALTER DATABASE "{APP_DATABASE}" RENAME TO "{restore_database}";\n'
                        )
                    self._postgres_admin(
                        f'ALTER DATABASE "{previous_database}" RENAME TO "{APP_DATABASE}";\n'
                    )
                if previous_data.exists() and not restore_committed:
                    failed_data = self.paths.state_root / f".data-failed-{secrets.token_hex(5)}"
                    if self.paths.application_data.exists():
                        os.replace(self.paths.application_data, failed_data)
                    os.replace(previous_data, self.paths.application_data)
                    if failed_data.exists():
                        remove_tree_within(failed_data, self.paths.state_root)
                if not restore_committed:
                    self._drop_database(restore_database)
                raise
            finally:
                remove_tree_within(staging, self.paths.state_root)

    def update(self, *, revision: str) -> None:
        self._require_root()
        if not REF_PATTERN.fullmatch(revision):
            raise DeploymentError(
                "--ref must be a full lowercase 40-character Git SHA.", exit_code=3
            )
        with InstallationLock(self.paths.run_root / "update.lock"):
            deployment = self._deployment()
            previous = self._current_release()
            previous_ref = self._validate_checkout(previous)
            if previous_ref == revision:
                print("Requested revision is already active; validating installation.")
                self.start()
                return
            repository = str(deployment.get("repository", REPOSITORY_URL))
            candidate = self._prepare_release(repository, revision)
            build = self._build_release(candidate)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            rollback_backup = (
                self.paths.backup_root / f"pre-update-{timestamp}-{previous_ref[:12]}.tar.gz"
            )
            self.backup(rollback_backup)
            deployment = self._deployment()
            rollback_manifest = dict(deployment)
            self._stop_service("video-factory-worker")
            self._stop_service("video-factory-api")
            self._stop_service("video-factory-nginx")
            values = parse_env_file(self.paths.env_file)
            try:
                self._apply_migrations(candidate, values)
                self._activate_release(candidate)
                self._render_configs()
                deployment["deployed_ref"] = revision
                deployment["updated_at"] = utc_now()
                deployment["build"] = build
                deployment["previous_release"] = {
                    "ref": previous_ref,
                    "rollback_backup": str(rollback_backup),
                }
                atomic_json(self.paths.deployment_manifest, deployment, mode=0o640)
                self.start()
                if values.get("VIDEO_APP_BACKEND") == "fake":
                    self.smoke_test(deadline_seconds=60)
            except BaseException:
                self._activate_release(previous)
                self._render_configs()
                rollback_manifest["deployed_ref"] = previous_ref
                rollback_manifest["updated_at"] = utc_now()
                rollback_manifest["failed_update"] = {
                    "target_ref": revision,
                    "pre_update_backup": str(rollback_backup),
                    "schema_may_be_forward_migrated": True,
                }
                atomic_json(self.paths.deployment_manifest, rollback_manifest, mode=0o640)
                raise
        print(f"Updated Video Factory from {previous_ref} to {revision}.")
        print(f"Pre-update recovery backup: {rollback_backup}")

    def rotate_database_password(self, password_file: Path | None) -> None:
        self._require_root()
        values = parse_env_file(self.paths.env_file)
        _, old_password, _, _ = parse_database_url(values["DATABASE_URL"])
        new_password = (
            read_private_secret(password_file, label="Database password")
            if password_file is not None
            else secrets.token_urlsafe(36)
        )
        escaped = new_password.replace("'", "''")
        old_values = dict(values)
        self._postgres_admin(f"ALTER ROLE {APP_ROLE} PASSWORD '{escaped}';\n")
        values["DATABASE_URL"] = database_url(password=new_password)
        try:
            atomic_write(self.paths.env_file, serialize_environment(values), mode=0o600)
            self._supervisorctl("restart", "video-factory-api", "video-factory-worker")
            if not self._check_database_authentication(values):
                raise DeploymentError(
                    "Rotated database credentials failed validation.", exit_code=6
                )
        except BaseException:
            rollback = old_password.replace("'", "''")
            self._postgres_admin(f"ALTER ROLE {APP_ROLE} PASSWORD '{rollback}';\n")
            atomic_write(self.paths.env_file, serialize_environment(old_values), mode=0o600)
            self._supervisorctl("restart", "video-factory-api", "video-factory-worker", check=False)
            raise
        print("Database password rotated; the value was not printed or logged.")

    def foreground(self) -> NoReturn:
        self.start()
        stopping = False

        def request_stop(_signum: int, _frame: object) -> None:
            nonlocal stopping
            stopping = True

        signal.signal(signal.SIGTERM, request_stop)
        signal.signal(signal.SIGINT, request_stop)
        while not stopping:
            states = self._service_states()
            failed = [name for name, state in states.items() if state != "RUNNING"]
            if failed:
                raise DeploymentError(
                    "Managed service stopped unexpectedly: " + ", ".join(failed), exit_code=6
                )
            time.sleep(2)
        self.stop()
        raise SystemExit(0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="runpodctl",
        description="Manage one isolated Video Factory installation inside a RunPod Pod.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    install = subparsers.add_parser("install", help="Install an exact Git revision.")
    install.add_argument("--repository", default=REPOSITORY_URL)
    install.add_argument("--ref", required=True, dest="revision")
    install.add_argument("--accept-ephemeral", action="store_true")
    source = install.add_mutually_exclusive_group(required=True)
    source.add_argument("--initialize-empty-database", action="store_true")
    source.add_argument("--restore", type=Path, dest="restore_archive")
    install.add_argument("--password-file", type=Path)
    install.add_argument("--owner-id", default="local-owner")

    for name in ("start", "stop", "restart", "foreground"):
        subparsers.add_parser(name)
    status = subparsers.add_parser("status")
    status.add_argument("--json", action="store_true", dest="output_json")
    doctor = subparsers.add_parser("doctor")
    doctor.add_argument("--json", action="store_true", dest="output_json")
    logs = subparsers.add_parser("logs")
    logs.add_argument(
        "--service",
        choices=(
            "supervisor",
            "postgres",
            "api",
            "worker",
            "nginx",
            "nginx-error",
            "tailscale",
        ),
    )
    logs.add_argument("--lines", type=int, default=200)
    update = subparsers.add_parser("update")
    update.add_argument("--ref", required=True, dest="revision")
    backup = subparsers.add_parser("backup")
    backup.add_argument("--output", required=True, type=Path)
    restore = subparsers.add_parser("restore")
    restore.add_argument("--archive", required=True, type=Path)
    restore.add_argument("--replace-existing", action="store_true")
    restore.add_argument("--confirm")
    smoke = subparsers.add_parser("smoke-test")
    smoke.add_argument("--deadline-seconds", type=int, default=60)
    tailscale = subparsers.add_parser("tailscale-login")
    tailscale.add_argument("--auth-key-file", type=Path)
    rotation = subparsers.add_parser("rotate-db-password")
    rotation.add_argument("--password-file", type=Path)
    return parser


def dispatch(manager: DeploymentManager, arguments: argparse.Namespace) -> None:
    command = arguments.command
    if command == "install":
        manager.install(
            repository=arguments.repository,
            revision=arguments.revision,
            accept_ephemeral=arguments.accept_ephemeral,
            initialize_empty_database=arguments.initialize_empty_database,
            restore_archive=arguments.restore_archive,
            password_file=arguments.password_file,
            owner_id=arguments.owner_id,
        )
    elif command == "start":
        manager.start()
    elif command == "stop":
        manager.stop()
    elif command == "restart":
        manager.restart()
    elif command == "foreground":
        manager.foreground()
    elif command == "status":
        manager.status(output_json=arguments.output_json)
    elif command == "doctor":
        manager.doctor(output_json=arguments.output_json)
    elif command == "logs":
        manager.logs(service=arguments.service, lines=arguments.lines)
    elif command == "update":
        manager.update(revision=arguments.revision)
    elif command == "backup":
        manager.backup(arguments.output)
    elif command == "restore":
        manager.restore(
            arguments.archive,
            replace_existing=arguments.replace_existing,
            confirmation=arguments.confirm,
        )
    elif command == "smoke-test":
        if not 5 <= arguments.deadline_seconds <= 3600:
            raise DeploymentError(
                "Smoke-test deadline must be 5 through 3600 seconds.", exit_code=3
            )
        manager.smoke_test(deadline_seconds=arguments.deadline_seconds)
    elif command == "tailscale-login":
        manager.tailscale_login(arguments.auth_key_file)
    elif command == "rotate-db-password":
        manager.rotate_database_password(arguments.password_file)
    else:  # pragma: no cover - argparse enforces a known command
        raise DeploymentError("Unknown command.", exit_code=3)


def main(arguments: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parsed = parser.parse_args(arguments)
    manager = DeploymentManager(DeploymentPaths.from_environment())
    try:
        dispatch(manager, parsed)
    except DeploymentError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return error.exit_code
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
