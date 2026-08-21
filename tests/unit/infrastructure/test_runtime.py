from __future__ import annotations

import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from video_app.infrastructure.runtime import (
    RuntimeSettings,
    SecureIdentifiers,
    SecureSeedSource,
)


def _values(data_root: Path) -> dict[str, str]:
    return {
        "DATABASE_URL": "postgresql+asyncpg://user:password@127.0.0.1:5433/database",
        "VIDEO_APP_DATA_ROOT": str(data_root),
        "VIDEO_APP_CURSOR_SECRET": "a" * 32,
        "VIDEO_APP_BACKEND": "fake",
        "VIDEO_APP_MODEL_ID": "wan21-t2v",
        "VIDEO_APP_MODEL_DISPLAY_NAME": "Wan2.1 Text to Video",
        "VIDEO_APP_MODEL_RESOLUTIONS": "832x480,1280x720",
        "VIDEO_APP_MODEL_FRAME_COUNTS": "81,121",
    }


def _wan21_values(
    data_root: Path,
    repository_root: Path,
    checkpoint_dir: Path,
) -> dict[str, str]:
    values = _values(data_root)
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


class RuntimeSettingsTests(unittest.TestCase):
    def test_parses_explicit_capability_without_generation_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            settings = RuntimeSettings.from_values(_values(root))

        self.assertEqual(settings.data_root, root)
        self.assertEqual(settings.capability.model_id, "wan21-t2v")
        self.assertEqual(
            {(item.width, item.height) for item in settings.capability.resolutions},
            {(832, 480), (1280, 720)},
        )
        self.assertEqual(settings.capability.frame_counts, frozenset({81, 121}))
        self.assertIsNone(settings.wan21)

    def test_parses_wan21_settings_only_when_backend_is_selected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            repository_root = root / "Wan2.1"
            checkpoint_dir = root / "checkpoints"
            repository_root.mkdir()
            checkpoint_dir.mkdir()

            settings = RuntimeSettings.from_values(
                _wan21_values(root, repository_root, checkpoint_dir)
            )

        self.assertEqual(settings.backend_name, "wan21")
        self.assertIsNotNone(settings.wan21)
        assert settings.wan21 is not None
        self.assertEqual(settings.wan21.repository_root, repository_root)
        self.assertEqual(settings.wan21.checkpoint_dir, checkpoint_dir)
        self.assertEqual(settings.wan21.python_executable, Path(sys.executable).resolve())
        self.assertEqual(settings.wan21.task, "t2v-1.3B")
        self.assertEqual(
            settings.wan21.model_revision,
            "37ec512624d61f7aa208f7ea8140a131f93afc9a",
        )

    def test_wan21_backend_requires_complete_adapter_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            repository_root = root / "Wan2.1"
            checkpoint_dir = root / "checkpoints"
            repository_root.mkdir()
            checkpoint_dir.mkdir()
            configured = _wan21_values(root, repository_root, checkpoint_dir)

            for name in (
                "VIDEO_APP_WAN21_REPOSITORY_ROOT",
                "VIDEO_APP_WAN21_CHECKPOINT_DIR",
                "VIDEO_APP_WAN21_PYTHON",
                "VIDEO_APP_WAN21_TASK",
                "VIDEO_APP_WAN21_MODEL_REVISION",
            ):
                with self.subTest(name=name):
                    incomplete = dict(configured)
                    del incomplete[name]
                    with self.assertRaisesRegex(RuntimeError, name):
                        RuntimeSettings.from_values(incomplete)

    def test_wan21_backend_rejects_relative_runtime_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            repository_root = root / "Wan2.1"
            checkpoint_dir = root / "checkpoints"
            repository_root.mkdir()
            checkpoint_dir.mkdir()
            configured = _wan21_values(root, repository_root, checkpoint_dir)

            for name in (
                "VIDEO_APP_WAN21_REPOSITORY_ROOT",
                "VIDEO_APP_WAN21_CHECKPOINT_DIR",
                "VIDEO_APP_WAN21_PYTHON",
            ):
                with self.subTest(name=name):
                    invalid = dict(configured)
                    invalid[name] = "relative/path"
                    with self.assertRaises(ValueError):
                        RuntimeSettings.from_values(invalid)

    def test_rejects_unknown_backend(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            values = _values(Path(directory).resolve())
            values["VIDEO_APP_BACKEND"] = "unknown"

            with self.assertRaisesRegex(ValueError, "fake or wan21"):
                RuntimeSettings.from_values(values)

    def test_dataclass_rejects_inconsistent_backend_specific_settings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            repository_root = root / "Wan2.1"
            checkpoint_dir = root / "checkpoints"
            repository_root.mkdir()
            checkpoint_dir.mkdir()
            fake = RuntimeSettings.from_values(_values(root))
            wan21 = RuntimeSettings.from_values(
                _wan21_values(root, repository_root, checkpoint_dir)
            )

            with self.assertRaisesRegex(ValueError, "present only"):
                replace(fake, backend_name="wan21")
            with self.assertRaisesRegex(ValueError, "present only"):
                replace(wan21, backend_name="fake")

    def test_fake_backend_ignores_malformed_wan21_only_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            values = _values(Path(directory).resolve())
            values.update(
                {
                    "VIDEO_APP_WAN21_REPOSITORY_ROOT": "relative/repository",
                    "VIDEO_APP_WAN21_CHECKPOINT_DIR": "",
                    "VIDEO_APP_WAN21_PYTHON": "not-an-absolute-python",
                    "VIDEO_APP_WAN21_TASK": "   ",
                    "VIDEO_APP_WAN21_MODEL_REVISION": "",
                }
            )

            settings = RuntimeSettings.from_values(values)

        self.assertEqual(settings.backend_name, "fake")
        self.assertIsNone(settings.wan21)

    def test_rejects_relative_data_root_and_short_secret(self) -> None:
        relative = _values(Path("relative"))
        with self.assertRaises(ValueError):
            RuntimeSettings.from_values(relative)

        with tempfile.TemporaryDirectory() as directory:
            short_secret = _values(Path(directory).resolve())
            short_secret["VIDEO_APP_CURSOR_SECRET"] = "short"
            with self.assertRaises(ValueError):
                RuntimeSettings.from_values(short_secret)

    def test_environment_file_rejects_malformed_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "invalid.env"
            path.write_text("NOT_AN_ENVIRONMENT_ENTRY", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                RuntimeSettings.from_file(path)

    def test_secure_identifiers_and_seed_are_valid(self) -> None:
        identifiers = SecureIdentifiers()
        job_ids = {identifiers.new_job_id() for _ in range(10)}
        seed = SecureSeedSource().new_seed()

        self.assertEqual(len(job_ids), 10)
        self.assertTrue(all(item.startswith("job_") for item in job_ids))
        self.assertGreaterEqual(seed, 0)
        self.assertLessEqual(seed, 2**63 - 1)


if __name__ == "__main__":
    unittest.main()
