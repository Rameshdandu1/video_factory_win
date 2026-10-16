from __future__ import annotations

import json
import os
import socket
import tarfile
import tempfile
import threading
import unittest
from collections.abc import Mapping, Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from unittest.mock import patch

from deploy.runpod.runpod_deploy import (
    SERVICE_NAMES,
    CommandResult,
    CommandRunner,
    DeploymentError,
    DeploymentManager,
    DeploymentPaths,
    database_url,
    database_url_with_name,
    demo_environment,
    ensure_safe_archive_members,
    parse_database_url,
    parse_env_file,
    parse_listening_ports,
    redact_text,
    render_template,
    serialize_environment,
    sha256_file,
    tree_checksums,
)


def _paths(root: Path) -> DeploymentPaths:
    return DeploymentPaths(
        install_root=(root / "install").resolve(),
        config_root=(root / "config").resolve(),
        state_root=(root / "state").resolve(),
        log_root=(root / "log").resolve(),
        run_root=(root / "run").resolve(),
    )


def _write_valid_environment(paths: DeploymentPaths, *, password: str = "valid-password") -> str:
    paths.config_root.mkdir(parents=True, exist_ok=True)
    paths.application_data.mkdir(parents=True, exist_ok=True)
    content = serialize_environment(demo_environment(paths, password=password, owner_id="owner"))
    paths.env_file.write_text(content, encoding="utf-8")
    return content


def _start_http_server(
    status: int, body: bytes
) -> tuple[ThreadingHTTPServer, threading.Thread, str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *_arguments: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, f"http://127.0.0.1:{server.server_port}/"


class LifecycleManager(DeploymentManager):
    def __init__(self, paths: DeploymentPaths) -> None:
        super().__init__(paths)
        self.states = {name: "STOPPED" for name in SERVICE_NAMES}
        self.starts = {name: 0 for name in SERVICE_NAMES}
        self.release = paths.install_root / "releases" / ("a" * 40)
        self.release.mkdir(parents=True)

    def _require_root(self) -> None:
        return

    def _current_release(self) -> Path:
        return self.release

    def _validate_checkout(self, release: Path) -> str:
        self.assert_release(release)
        return "a" * 40

    def assert_release(self, release: Path) -> None:
        if release != self.release:
            raise AssertionError("unexpected release")

    def _render_configs(self, postgres_port: int = 5432) -> None:
        if postgres_port != 5432:
            raise AssertionError("unexpected port")

    def _validate_postgres_compatibility(self) -> None:
        return

    def _ensure_supervisor(self) -> None:
        return

    def _service_states(self) -> dict[str, str]:
        return dict(self.states)

    def _assert_managed_ports_available(self, states: Mapping[str, str]) -> None:
        if dict(states) != self.states:
            raise AssertionError("unexpected states")

    def _start_service(self, name: str) -> None:
        if self.states[name] != "RUNNING":
            self.starts[name] += 1
            self.states[name] = "RUNNING"

    def _wait_postgres(self, values: Mapping[str, str], *, deadline_seconds: int = 30) -> None:
        if not values:
            raise AssertionError("environment was not loaded")

    def _check_database_authentication(self, values: Mapping[str, str]) -> bool:
        return bool(values)

    def _validate_schema(self, release: Path, values: Mapping[str, str]) -> None:
        self.assert_release(release)
        if not values:
            raise AssertionError("environment was not loaded")

    def _wait_http(self, url: str, *, deadline_seconds: int = 30) -> None:
        if not url.startswith("http://127.0.0.1:") or deadline_seconds != 30:
            raise AssertionError("unexpected readiness probe")

    def _wait_tailscale_daemon(self, *, deadline_seconds: int = 20) -> None:
        if deadline_seconds != 20:
            raise AssertionError("unexpected Tailscale deadline")

    def _tailscale_authorized(self) -> bool:
        return False


class ExistingInstallManager(DeploymentManager):
    def __init__(self, paths: DeploymentPaths, release: Path) -> None:
        super().__init__(paths)
        self.release = release
        self.activated = False

    def _require_root(self) -> None:
        return

    def _validate_postgres_compatibility(self) -> None:
        return

    def _set_directory_owner(self, path: Path, owner: str) -> None:
        del path, owner

    def _prepare_release(self, repository: str, revision: str) -> Path:
        if not repository.endswith("video_factory_win.git") or revision != "a" * 40:
            raise AssertionError("unexpected release request")
        return self.release

    def _build_release(self, release: Path) -> dict[str, object]:
        if release != self.release:
            raise AssertionError("unexpected release")
        return {"cached": True}

    def _activate_release(self, release: Path) -> None:
        if release != self.release:
            raise AssertionError("unexpected release")
        self.activated = True

    def _render_configs(self, postgres_port: int = 5432) -> None:
        if not self.activated or postgres_port != 5432:
            raise AssertionError("release was not activated")


class ResumeInstallManager(ExistingInstallManager):
    def __init__(self, paths: DeploymentPaths, release: Path) -> None:
        super().__init__(paths, release)
        self.completed = False

    def _complete_installation(
        self,
        manifest: dict[str, Any],
        release: Path,
        values: Mapping[str, str],
        restore_archive: Path | None,
    ) -> None:
        if manifest.get("install_state") != "initializing":
            raise AssertionError("resume did not preserve initializing state")
        if release != self.release or not values or restore_archive is not None:
            raise AssertionError("resume inputs changed")
        self.completed = True


class PortConflictManager(DeploymentManager):
    def _listening_ports(self) -> dict[int, str]:
        return {8000: 'users:(("foreign",pid=77,fd=3))'}


class DoctorHttpManager(DeploymentManager):
    def __init__(self, paths: DeploymentPaths, result: dict[str, Any]) -> None:
        super().__init__(paths)
        self.result = result
        self.release = paths.install_root / "release"
        self.release.mkdir(parents=True)

    def _current_release(self) -> Path:
        return self.release

    def _validate_checkout(self, release: Path) -> str:
        if release != self.release:
            raise AssertionError("unexpected release")
        return "a" * 40

    def _service_states(self) -> dict[str, str]:
        return {name: "RUNNING" for name in SERVICE_NAMES}

    def _check_database_authentication(self, values: Mapping[str, str]) -> bool:
        return bool(values)

    def _schema_status(self, release: Path, values: Mapping[str, str]) -> dict[str, Any]:
        if release != self.release or not values:
            raise AssertionError("unexpected schema inputs")
        return {"state": "current", "heads": ["head"], "current": ["head"]}

    def _listening_ports(self) -> dict[int, str]:
        return {}

    def _tailscale_status(self) -> dict[str, Any]:
        return {"daemon": "ready", "authorization": "authorized"}

    def _tailscale_serve_status(self) -> dict[str, Any]:
        return {"configured": True, "state": "private_https"}

    def _frontend_http_status(self) -> dict[str, Any]:
        return dict(self.result)

    def _api_http_status(self, url: str) -> dict[str, Any]:
        if not url.endswith("/api/v1/health"):
            raise AssertionError("unexpected API health URL")
        return dict(self.result)


class StaticRunner(CommandRunner):
    def __init__(self, result: CommandResult) -> None:
        self.result = result

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
        del arguments, cwd, environment, input_text, check, capture, timeout
        return self.result


class RunPodConfigurationTests(unittest.TestCase):
    def test_database_password_is_url_escaped_and_round_trips(self) -> None:
        password = "@:#/%' quoted password"
        url = database_url(password=password)
        self.assertNotIn(password, url)
        self.assertEqual(parse_database_url(url), ("video_app", password, "video_factory", 5432))

    def test_database_name_replacement_preserves_credentials(self) -> None:
        original = database_url(password="p@ss:word")
        replaced = database_url_with_name(original, "video_factory_restore_123")
        self.assertEqual(
            parse_database_url(replaced),
            ("video_app", "p@ss:word", "video_factory_restore_123", 5432),
        )

    def test_environment_preserves_spaces_without_shell_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = _paths(Path(temporary))
            content = _write_valid_environment(paths)
            content += "VIDEO_APP_OPTIONAL_LABEL=label with spaces\n"
            paths.env_file.write_text(content, encoding="utf-8")
            values = parse_env_file(paths.env_file)
        self.assertEqual(values["VIDEO_APP_OPTIONAL_LABEL"], "label with spaces")

    def test_environment_rejects_duplicate_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = _paths(Path(temporary))
            content = _write_valid_environment(paths)
            paths.env_file.write_text(content + "VIDEO_APP_BACKEND=fake\n", encoding="utf-8")
            with self.assertRaisesRegex(DeploymentError, "Duplicate"):
                parse_env_file(paths.env_file)

    def test_environment_rejects_malformed_driver_placeholder_and_relative_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = _paths(Path(temporary))
            valid = demo_environment(paths, password="password", owner_id="owner")
            invalid_values = (
                {**valid, "DATABASE_URL": "postgresql://user:pass@127.0.0.1/db"},
                {**valid, "VIDEO_APP_OWNER_ID": "replace-with-owner"},
                {**valid, "VIDEO_APP_DATA_ROOT": "relative/data"},
            )
            paths.config_root.mkdir(parents=True)
            for values in invalid_values:
                paths.env_file.write_text(serialize_environment(values), encoding="utf-8")
                with self.assertRaises(DeploymentError):
                    parse_env_file(paths.env_file)

    def test_migration_environment_overrides_stale_terminal_database_url(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = _paths(root)
            manager = DeploymentManager(paths)
            expected = database_url(password="selected")
            old_value = os.environ.get("DATABASE_URL")
            os.environ["DATABASE_URL"] = "postgresql+asyncpg://stale"
            try:
                environment = manager._migration_environment(
                    root / "release", {"DATABASE_URL": expected}
                )
            finally:
                if old_value is None:
                    os.environ.pop("DATABASE_URL", None)
                else:
                    os.environ["DATABASE_URL"] = old_value
        self.assertEqual(environment["DATABASE_URL"], expected)


class RunPodHttpDiagnosticTests(unittest.TestCase):
    def _probe(
        self,
        status: int,
        body: bytes,
        *,
        expected_text: Sequence[str] = (),
        expected_json: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        server, thread, url = _start_http_server(status, body)
        try:
            with tempfile.TemporaryDirectory() as temporary:
                manager = DeploymentManager(_paths(Path(temporary)))
                return manager._http_status(
                    url, expected_text=expected_text, expected_json=expected_json
                )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_valid_frontend_and_api_responses_are_healthy(self) -> None:
        frontend = self._probe(
            200,
            b'<html><title>Video Factory</title><div id="root"></div></html>',
            expected_text=("<title>Video Factory</title>", '<div id="root"></div>'),
        )
        api = self._probe(200, b'{"status":"ok"}', expected_json={"status": "ok"})
        self.assertTrue(frontend["reachable"])
        self.assertTrue(frontend["healthy"])
        self.assertTrue(frontend["content_valid"])
        self.assertTrue(api["reachable"])
        self.assertTrue(api["healthy"])
        self.assertTrue(api["content_valid"])

    def test_http_403_and_502_are_reachable_but_unhealthy(self) -> None:
        for status in (403, 502):
            with self.subTest(status=status):
                result = self._probe(status, b'{"status":"ok"}', expected_json={"status": "ok"})
                self.assertTrue(result["reachable"])
                self.assertFalse(result["healthy"])
                self.assertEqual(result["status"], status)
                self.assertEqual(result["failure"], "unexpected_status")

    def test_connection_refusal_and_timeout_are_transport_failures(self) -> None:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        with tempfile.TemporaryDirectory() as temporary:
            manager = DeploymentManager(_paths(Path(temporary)))
            refused = manager._http_status(
                f"http://127.0.0.1:{port}/", expected_json={"status": "ok"}
            )
            with patch(
                "deploy.runpod.runpod_deploy.urllib.request.urlopen",
                side_effect=TimeoutError("timed out"),
            ):
                timed_out = manager._http_status(
                    "http://127.0.0.1:1/", expected_json={"status": "ok"}
                )
        for result in (refused, timed_out):
            self.assertFalse(result["reachable"])
            self.assertFalse(result["healthy"])
            self.assertEqual(result["failure"], "transport_error")

    def test_http_200_with_wrong_body_is_unhealthy(self) -> None:
        frontend = self._probe(
            200,
            b"<html><title>Proxy error</title></html>",
            expected_text=("<title>Video Factory</title>", '<div id="root"></div>'),
        )
        api = self._probe(200, b'{"status":"degraded"}', expected_json={"status": "ok"})
        for result in (frontend, api):
            self.assertTrue(result["reachable"])
            self.assertFalse(result["healthy"])
            self.assertFalse(result["content_valid"])
            self.assertEqual(result["failure"], "unexpected_content")

    def test_doctor_uses_application_health_not_transport_reachability(self) -> None:
        failure = {
            "reachable": True,
            "healthy": False,
            "status": 502,
            "content_valid": False,
            "failure": "unexpected_status",
        }
        with tempfile.TemporaryDirectory() as temporary:
            paths = _paths(Path(temporary))
            _write_valid_environment(paths)
            payload = DoctorHttpManager(paths, failure).doctor_payload()
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertEqual(checks["frontend-http"]["state"], "fail")
        self.assertEqual(checks["api-http"]["state"], "fail")


class RunPodLifecycleTests(unittest.TestCase):
    def test_repeated_start_starts_exactly_one_worker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = _paths(Path(temporary))
            _write_valid_environment(paths)
            manager = LifecycleManager(paths)
            manager.start()
            manager.start()
        self.assertEqual(manager.starts["video-factory-worker"], 1)
        self.assertTrue(all(count == 1 for count in manager.starts.values()))

    def test_repeated_install_preserves_configuration_and_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = _paths(Path(temporary))
            existing_config = _write_valid_environment(paths, password="do-not-rotate")
            paths.state_root.mkdir(parents=True, exist_ok=True)
            paths.deployment_manifest.write_text(
                json.dumps({"deployed_ref": "a" * 40}), encoding="utf-8"
            )
            marker = paths.application_data / "existing-record.bin"
            marker.write_bytes(b"preserve-me")
            release = paths.releases_root / ("a" * 40)
            release.mkdir(parents=True)
            manager = ExistingInstallManager(paths, release)
            manager.install(
                repository="https://github.com/Rameshdandu1/video_factory_win.git",
                revision="a" * 40,
                accept_ephemeral=True,
                initialize_empty_database=True,
                restore_archive=None,
                password_file=None,
                owner_id="different-owner",
            )
            self.assertEqual(paths.env_file.read_text(encoding="utf-8"), existing_config)
            self.assertEqual(marker.read_bytes(), b"preserve-me")

    def test_interrupted_authorized_install_resumes_without_reinitializing_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = _paths(Path(temporary))
            existing_config = _write_valid_environment(paths, password="preserved-password")
            paths.state_root.mkdir(parents=True, exist_ok=True)
            paths.deployment_manifest.write_text(
                json.dumps(
                    {
                        "deployed_ref": "a" * 40,
                        "install_state": "initializing",
                        "initialization_mode": "empty",
                    }
                ),
                encoding="utf-8",
            )
            marker = paths.application_data / "interrupted-record.bin"
            marker.write_bytes(b"keep")
            release = paths.releases_root / ("a" * 40)
            release.mkdir(parents=True)
            manager = ResumeInstallManager(paths, release)
            manager.install(
                repository="https://github.com/Rameshdandu1/video_factory_win.git",
                revision="a" * 40,
                accept_ephemeral=True,
                initialize_empty_database=True,
                restore_archive=None,
                password_file=None,
                owner_id="ignored-on-resume",
            )
            self.assertTrue(manager.completed)
            self.assertEqual(paths.env_file.read_text(encoding="utf-8"), existing_config)
            self.assertEqual(marker.read_bytes(), b"keep")

    def test_unrelated_port_is_reported_not_killed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manager = PortConflictManager(_paths(Path(temporary)))
            with self.assertRaisesRegex(DeploymentError, "outside this deployment"):
                manager._assert_managed_ports_available({name: "STOPPED" for name in SERVICE_NAMES})

    def test_ss_listener_parser_retains_process_identity(self) -> None:
        listeners = parse_listening_ports(
            'LISTEN 0 4096 127.0.0.1:8000 0.0.0.0:* users:(("uvicorn",pid=9,fd=7))\n'
        )
        self.assertIn("uvicorn", listeners[8000])

    def test_tailscale_daemon_and_authorization_failures_are_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = _paths(Path(temporary))
            unavailable = DeploymentManager(paths, StaticRunner(CommandResult(1, "", "failed")))
            login_required = DeploymentManager(
                paths,
                StaticRunner(
                    CommandResult(
                        1,
                        json.dumps({"BackendState": "NeedsLogin", "Self": {}}),
                        "",
                    )
                ),
            )
            approval_required = DeploymentManager(
                paths,
                StaticRunner(
                    CommandResult(
                        0,
                        json.dumps({"BackendState": "NeedsMachineAuth", "Self": {}}),
                        "",
                    )
                ),
            )
            self.assertEqual(unavailable._tailscale_status()["daemon"], "unavailable")
            self.assertEqual(login_required._tailscale_status()["authorization"], "login_required")
            self.assertEqual(
                approval_required._tailscale_status()["authorization"], "approval_required"
            )


class RunPodSecurityTests(unittest.TestCase):
    def test_archive_traversal_and_links_are_rejected(self) -> None:
        traversal = tarfile.TarInfo("../escape")
        traversal.size = 0
        link = tarfile.TarInfo("data/link")
        link.type = tarfile.SYMTYPE
        with self.assertRaises(DeploymentError):
            ensure_safe_archive_members((traversal,))
        with self.assertRaises(DeploymentError):
            ensure_safe_archive_members((link,))

    def test_log_redaction_removes_database_urls_auth_keys_and_seeded_secrets(self) -> None:
        secret = "seeded-secret-value"
        message = (
            f"value={secret} database=postgresql+asyncpg://user:p%40ss@127.0.0.1/db "
            "key=tskey-auth-example login=https://login.tailscale.com/example"
        )
        redacted = redact_text(message, (secret,))
        self.assertNotIn(secret, redacted)
        self.assertNotIn("p%40ss", redacted)
        self.assertNotIn("tskey-auth", redacted)
        self.assertNotIn("login.tailscale.com", redacted)

    def test_template_rendering_rejects_unresolved_values(self) -> None:
        with self.assertRaises(DeploymentError):
            render_template("path=@@MISSING@@", {})

    def test_backup_extraction_verifies_and_recovers_sample_media(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            (source / "data").mkdir(parents=True)
            sample = source / "data" / "sample.mp4"
            sample.write_bytes(b"sample-media")
            dump = source / "database.dump"
            dump.write_bytes(b"sample-database")
            manifest = {
                "format": 1,
                "database_sha256": sha256_file(dump),
                "application_data_sha256": tree_checksums(source / "data"),
            }
            (source / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            archive_path = root / "backup.tar.gz"
            with tarfile.open(archive_path, "w:gz") as archive:
                archive.add(source / "manifest.json", arcname="manifest.json")
                archive.add(dump, arcname="database.dump")
                archive.add(source / "data", arcname="data")
            destination = root / "restored"
            destination.mkdir()
            manager = DeploymentManager(_paths(root / "deployment"))
            metadata = manager._extract_backup(archive_path, destination)
            recovered_media = (destination / "data" / "sample.mp4").read_bytes()
        self.assertEqual(metadata["format"], 1)
        self.assertEqual(recovered_media, b"sample-media")


class RunPodConfigurationTemplateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = Path(__file__).resolve().parents[2]

    def test_supervisor_uses_private_socket_and_one_worker(self) -> None:
        config = (self.repository / "deploy/runpod/supervisord.conf.template").read_text(
            encoding="utf-8"
        )
        self.assertIn("chmod=0600", config)
        self.assertNotIn("[inet_http_server]", config)
        worker = config.split("[program:video-factory-worker]", 1)[1].split("[program:", 1)[0]
        self.assertIn("numprocs=1", worker)
        self.assertIn("autorestart=unexpected", worker)
        self.assertIn("stopasgroup=true", worker)
        self.assertIn("nodaemon=false", config)
        self.assertIn("unix_socket_permissions=0700", config)

    def test_nginx_keeps_api_prefix_and_never_falls_back_for_assets(self) -> None:
        config = (self.repository / "deploy/runpod/nginx.conf.template").read_text(encoding="utf-8")
        self.assertIn("listen 127.0.0.1:5173", config)
        self.assertIn("proxy_pass http://127.0.0.1:8000;", config)
        self.assertIn("try_files $uri =404", config)
        self.assertIn("location ~ /\\.", config)
        self.assertNotIn("proxy_pass http://127.0.0.1:8000/;", config)

    def test_vite_development_host_allowlist_is_exact_not_wildcarded(self) -> None:
        config = (self.repository / "frontend/vite.config.ts").read_text(encoding="utf-8")
        self.assertIn("VIDEO_FACTORY_DEV_HOSTNAME", config)
        self.assertIn("allowedHosts: [developmentHostname]", config)
        self.assertNotIn("allowedHosts: true", config)
        self.assertNotIn("allowedHosts: ['.ts.net']", config)


if __name__ == "__main__":
    unittest.main()
