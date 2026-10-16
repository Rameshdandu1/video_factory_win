from __future__ import annotations

import os
import shutil
import stat
import sys
import tempfile
import unittest
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from deploy.runpod.runpod_deploy import (
    REPOSITORY_URL,
    SERVICE_NAMES,
    DeploymentManager,
    DeploymentPaths,
    parse_env_file,
)

ACCEPTANCE_ENABLED = (
    os.name == "posix" and os.environ.get("VIDEO_FACTORY_RUNPOD_INSTALLER_ACCEPTANCE") == "1"
)


def _paths(root: Path) -> DeploymentPaths:
    return DeploymentPaths(
        install_root=(root / "install").resolve(),
        config_root=(root / "config").resolve(),
        state_root=(root / "state").resolve(),
        log_root=(root / "log").resolve(),
        run_root=(root / "run").resolve(),
    )


def _prepare_release(repository: Path, release: Path) -> None:
    release.mkdir(parents=True)
    shutil.copy2(repository / "alembic.ini", release / "alembic.ini")
    shutil.copytree(repository / "migrations", release / "migrations")
    bin_directory = release / ".venv" / "bin"
    bin_directory.mkdir(parents=True)
    if " " in sys.executable:
        raise AssertionError("acceptance Python path must not contain spaces")
    alembic = bin_directory / "alembic"
    alembic.write_text(
        f"#!{sys.executable}\nfrom alembic.config import main\nmain()\n", encoding="utf-8"
    )
    os.chmod(alembic, 0o755)


class LinuxPostgresInstallerManager(DeploymentManager):
    def __init__(self, paths: DeploymentPaths, release: Path) -> None:
        super().__init__(paths)
        self.release = release
        self.postgres_started = False

    def _prepare_release(self, repository: str, revision: str) -> Path:
        if repository != REPOSITORY_URL or revision != "a" * 40:
            raise AssertionError("unexpected acceptance release")
        return self.release

    def _build_release(self, release: Path) -> dict[str, Any]:
        if release != self.release:
            raise AssertionError("unexpected release build")
        return {"acceptance": True}

    def _package_versions(self) -> dict[str, str]:
        return {"postgresql": "acceptance-system-package"}

    def _render_configs(self, postgres_port: int = 5432) -> None:
        if postgres_port != 5432:
            raise AssertionError("unexpected PostgreSQL port")

    def _ensure_supervisor(self) -> None:
        return

    def _assert_managed_ports_available(self, states: Mapping[str, str]) -> None:
        if any(state != "STOPPED" for state in states.values()):
            raise AssertionError("acceptance services started too early")

    def _service_states(self) -> dict[str, str]:
        states = {name: "STOPPED" for name in SERVICE_NAMES}
        if self.postgres_started:
            states["video-factory-postgres"] = "RUNNING"
        return states

    def _start_service(self, name: str) -> None:
        if name != "video-factory-postgres":
            raise AssertionError("acceptance test starts only PostgreSQL")
        if self.postgres_started:
            return
        if " " in str(self.paths.postgres_socket_dir):
            raise AssertionError("acceptance paths must not contain spaces")
        options = (
            "-c listen_addresses=127.0.0.1 "
            "-c port=5432 "
            f"-c unix_socket_directories={self.paths.postgres_socket_dir} "
            "-c unix_socket_permissions=0700 "
            "-c password_encryption=scram-sha-256"
        )
        self.runner.run(
            (
                "/usr/sbin/runuser",
                "-u",
                "postgres",
                "--",
                self._postgres_bin("pg_ctl"),
                "-D",
                self.paths.postgres_data,
                "-l",
                self.paths.postgres_data / "acceptance-postgres.log",
                "-o",
                options,
                "-w",
                "-t",
                "30",
                "start",
            )
        )
        self.postgres_started = True

    def start(self) -> None:
        return

    def stop_postgres(self) -> None:
        if not self.postgres_started:
            return
        self.runner.run(
            (
                "/usr/sbin/runuser",
                "-u",
                "postgres",
                "--",
                self._postgres_bin("pg_ctl"),
                "-D",
                self.paths.postgres_data,
                "-m",
                "fast",
                "-w",
                "-t",
                "30",
                "stop",
            ),
            check=False,
        )
        self.postgres_started = False


@unittest.skipUnless(
    ACCEPTANCE_ENABLED,
    "set VIDEO_FACTORY_RUNPOD_INSTALLER_ACCEPTANCE=1 on disposable Linux as root",
)
class RunPodInstallerAcceptanceTests(unittest.TestCase):
    def test_fresh_and_repeated_install_use_least_privilege_postgres_access(self) -> None:
        if not hasattr(os, "geteuid") or os.geteuid() != 0:
            self.fail("installer acceptance must run as root")
        repository = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory(prefix="video-factory-acceptance-") as temporary:
            root = Path(temporary).resolve()
            os.chmod(root, 0o711)
            paths = _paths(root)
            release = root / "acceptance-release"
            _prepare_release(repository, release)
            manager = LinuxPostgresInstallerManager(paths, release)
            try:
                postgres_uid = int(
                    manager.runner.run(("/usr/bin/id", "-u", "postgres")).stdout.strip()
                )
                postgres_gid = int(
                    manager.runner.run(("/usr/bin/id", "-g", "postgres")).stdout.strip()
                )
                self.assertNotEqual(postgres_uid, 0)
                manager.install(
                    repository=REPOSITORY_URL,
                    revision="a" * 40,
                    accept_ephemeral=True,
                    initialize_empty_database=True,
                    restore_archive=None,
                    password_file=None,
                    owner_id="acceptance-owner",
                )
                values = parse_env_file(paths.env_file)
                original_environment = paths.env_file.read_bytes()

                self.assertEqual(stat.S_IMODE(paths.state_root.stat().st_mode), 0o710)
                self.assertEqual(paths.state_root.stat().st_uid, 0)
                self.assertEqual(paths.state_root.stat().st_gid, postgres_gid)
                self.assertEqual(stat.S_IMODE(paths.run_root.stat().st_mode), 0o710)
                self.assertEqual(paths.run_root.stat().st_uid, 0)
                self.assertEqual(paths.run_root.stat().st_gid, postgres_gid)
                self.assertEqual(stat.S_IMODE(paths.postgres_socket_dir.stat().st_mode), 0o700)
                self.assertEqual(paths.postgres_socket_dir.stat().st_uid, postgres_uid)
                self.assertEqual(paths.postgres_socket_dir.stat().st_gid, postgres_gid)
                self.assertEqual(paths.postgres_data.stat().st_uid, postgres_uid)
                self.assertEqual(stat.S_IMODE(paths.env_file.stat().st_mode), 0o600)

                socket_path = paths.postgres_socket_dir / ".s.PGSQL.5432"
                self.assertTrue(socket_path.is_socket())
                self.assertEqual(socket_path.stat().st_uid, postgres_uid)
                self.assertTrue(manager._check_database_authentication(values))
                manager._validate_schema(release, values)

                for parent in (paths.state_root, paths.run_root):
                    self.assertTrue(self._postgres_can(manager, "-x", parent))
                    self.assertFalse(self._postgres_can(manager, "-r", parent))
                    self.assertFalse(self._postgres_can(manager, "-w", parent))
                self.assertTrue(self._postgres_can(manager, "-w", paths.postgres_socket_dir))
                for protected in (
                    paths.config_root,
                    paths.tailscale_state,
                    paths.log_root,
                    paths.backup_root,
                    paths.application_data,
                ):
                    self.assertFalse(self._postgres_can(manager, "-r", protected))
                    self.assertFalse(self._postgres_can(manager, "-w", protected))

                manager.runner.run(
                    (
                        manager._postgres_bin("psql"),
                        "--no-psqlrc",
                        "--command",
                        "CREATE TABLE installer_acceptance_marker "
                        "(value text PRIMARY KEY); "
                        "INSERT INTO installer_acceptance_marker VALUES ('preserved');",
                    ),
                    environment=manager._database_environment(values),
                )

                manager.install(
                    repository=REPOSITORY_URL,
                    revision="a" * 40,
                    accept_ephemeral=True,
                    initialize_empty_database=True,
                    restore_archive=None,
                    password_file=None,
                    owner_id="ignored-on-repeat",
                )
                self.assertEqual(paths.env_file.read_bytes(), original_environment)
                self.assertTrue(manager._check_database_authentication(values))
                manager._validate_schema(release, values)
                preserved = manager.runner.run(
                    (
                        manager._postgres_bin("psql"),
                        "--no-psqlrc",
                        "--tuples-only",
                        "--no-align",
                        "--command",
                        "SELECT value FROM installer_acceptance_marker;",
                    ),
                    environment=manager._database_environment(values),
                )
                self.assertEqual(preserved.stdout.strip(), "preserved")
            finally:
                manager.stop_postgres()

    def _postgres_can(self, manager: LinuxPostgresInstallerManager, flag: str, path: Path) -> bool:
        result = manager.runner.run(
            ("/usr/sbin/runuser", "-u", "postgres", "--", "/usr/bin/test", flag, path),
            check=False,
        )
        return result.returncode == 0


if __name__ == "__main__":
    unittest.main()
