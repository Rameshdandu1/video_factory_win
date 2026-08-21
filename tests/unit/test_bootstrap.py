from __future__ import annotations

import sys
import tempfile
import unittest
from collections.abc import Coroutine
from pathlib import Path
from typing import Any, NoReturn
from unittest.mock import patch

from video_app.backends.fake import FakeBackend
from video_app.backends.wan21.adapter import Wan21Backend
from video_app.bootstrap import _build_generation_backend, create_api_app, worker_main
from video_app.infrastructure.runtime import RuntimeSettings

WAN21_REPOSITORY_REVISION = "9737cba9c1c3c4d04b33fcad41c111989865d315"


def _settings_values(data_root: Path) -> dict[str, str]:
    return {
        "DATABASE_URL": "postgresql+asyncpg://user:password@127.0.0.1:5433/database",
        "VIDEO_APP_DATA_ROOT": str(data_root),
        "VIDEO_APP_CURSOR_SECRET": "a" * 32,
        "VIDEO_APP_BACKEND": "fake",
        "VIDEO_APP_MODEL_ID": "wan21-t2v",
        "VIDEO_APP_MODEL_DISPLAY_NAME": "Wan2.1 Text to Video",
        "VIDEO_APP_MODEL_RESOLUTIONS": "832x480",
        "VIDEO_APP_MODEL_FRAME_COUNTS": "81",
    }


def _wan21_settings_values(
    data_root: Path,
    repository_root: Path,
    checkpoint_dir: Path,
) -> dict[str, str]:
    values = _settings_values(data_root)
    values.update(
        {
            "VIDEO_APP_BACKEND": "wan21",
            "VIDEO_APP_WAN21_REPOSITORY_ROOT": str(repository_root),
            "VIDEO_APP_WAN21_CHECKPOINT_DIR": str(checkpoint_dir),
            "VIDEO_APP_WAN21_PYTHON": str(Path(sys.executable).resolve()),
            "VIDEO_APP_WAN21_TASK": "t2v-1.3B",
            "VIDEO_APP_WAN21_MODEL_REVISION": "37ec512624d61f7aa208f7ea8140a131f93afc9a",
        }
    )
    return values


def _raise_keyboard_interrupt(coroutine: Coroutine[Any, Any, None]) -> NoReturn:
    coroutine.close()
    raise KeyboardInterrupt


def _raise_runtime_error(coroutine: Coroutine[Any, Any, None]) -> NoReturn:
    coroutine.close()
    raise RuntimeError("worker startup failed")


class WorkerMainTests(unittest.TestCase):
    def test_operator_interrupt_exits_without_propagating(self) -> None:
        with (
            patch.object(sys, "argv", ["video-app-worker", "--env-file", "ignored.env"]),
            patch("video_app.bootstrap._settings_from_file"),
            patch("video_app.bootstrap.asyncio.run", side_effect=_raise_keyboard_interrupt),
        ):
            worker_main()

    def test_unexpected_runtime_error_still_propagates(self) -> None:
        with (
            patch.object(sys, "argv", ["video-app-worker", "--env-file", "ignored.env"]),
            patch("video_app.bootstrap._settings_from_file"),
            patch("video_app.bootstrap.asyncio.run", side_effect=_raise_runtime_error),
            self.assertRaisesRegex(RuntimeError, "worker startup failed"),
        ):
            worker_main()


class WorkerBackendSelectionTests(unittest.TestCase):
    def test_builds_fake_backend_for_offline_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            temporary_root = root / "temporary"
            temporary_root.mkdir()
            settings = RuntimeSettings.from_values(_settings_values(root))

            backend = _build_generation_backend(settings, temporary_root)

        self.assertIsInstance(backend, FakeBackend)
        self.assertEqual(backend.name, "fake")

    def test_builds_wan21_backend_only_when_selected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            repository_root = root / "Wan2.1"
            checkpoint_dir = root / "checkpoints"
            temporary_root = root / "temporary"
            repository_root.mkdir()
            checkpoint_dir.mkdir()
            temporary_root.mkdir()
            (repository_root / "generate.py").write_text(
                "# pinned Wan2.1 entry point placeholder\n",
                encoding="utf-8",
            )
            settings = RuntimeSettings.from_values(
                _wan21_settings_values(root, repository_root, checkpoint_dir)
            )

            with patch(
                "video_app.backends.wan21.adapter._current_repository_revision",
                return_value=WAN21_REPOSITORY_REVISION,
            ):
                backend = _build_generation_backend(settings, temporary_root)

        self.assertIsInstance(backend, Wan21Backend)
        self.assertEqual(backend.name, "wan21")


class ApiBackendIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_wan21_api_does_not_construct_backend_or_require_runtime_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            missing_root = root / "not-installed"
            settings = RuntimeSettings.from_values(
                _wan21_settings_values(
                    root / "data",
                    missing_root / "Wan2.1",
                    missing_root / "checkpoints",
                )
            )
            with patch("video_app.bootstrap._build_generation_backend") as build_backend:
                app = create_api_app(settings)
                async with app.router.lifespan_context(app):
                    pass

            build_backend.assert_not_called()


if __name__ == "__main__":
    unittest.main()
