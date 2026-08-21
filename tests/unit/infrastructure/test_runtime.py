from __future__ import annotations

import tempfile
import unittest
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
