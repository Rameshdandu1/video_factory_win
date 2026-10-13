from __future__ import annotations

import json
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


def _wan22_values(data_root: Path) -> dict[str, str]:
    repository = data_root / "Wan2.2"
    checkpoint = data_root / "wan22-checkpoint"
    repository.mkdir()
    checkpoint.mkdir()
    report = data_root / "wan22-qualification.json"
    report.write_text(
        json.dumps(
            {
                "status": "approved",
                "code_revision": "1ea34ff48f87168174e12956e200b1d908b1c5ff",
                "model_revision": "921dbaf3f1674a56f47e83fb80a34bac8a8f203e",
                "task": "ti2v-5B",
                "checkpoint_manifest_sha256": "b" * 64,
                "input_conditioning_verified": True,
                "no_t2v_fallback_verified": True,
                "cancellation_cleanup_verified": True,
                "minimum_free_disk_bytes": 1_000,
                "minimum_free_vram_bytes": 2_000,
            }
        ),
        encoding="utf-8",
    )
    values = _values(data_root)
    values.update(
        {
            "VIDEO_APP_WAN22_TI2V_ENABLED": "true",
            "VIDEO_APP_WAN22_REPOSITORY_ROOT": str(repository),
            "VIDEO_APP_WAN22_CHECKPOINT_DIR": str(checkpoint),
            "VIDEO_APP_WAN22_PYTHON": str(Path(sys.executable).resolve()),
            "VIDEO_APP_WAN22_QUALIFICATION_REPORT": str(report),
            "VIDEO_APP_WAN22_CHECKPOINT_MANIFEST_SHA256": "b" * 64,
        }
    )
    return values


def _controlled_values(data_root: Path, *, provider: str = "vace") -> dict[str, str]:
    is_vace = provider == "vace"
    prefix = "VIDEO_APP_VACE" if is_vace else "VIDEO_APP_WAN_ANIMATE"
    repository = data_root / ("VACE" if is_vace else "Wan2.2")
    checkpoint = data_root / ("vace-checkpoint" if is_vace else "animate-checkpoint")
    repository.mkdir()
    checkpoint.mkdir()
    ffmpeg = data_root / "ffmpeg.exe"
    ffmpeg.write_bytes(b"qualified ffmpeg fixture")
    report = data_root / f"{provider}-qualification.json"
    checkpoint_sha = "b" * 64
    ffmpeg_sha = "c" * 64
    payload = {
        "status": "approved",
        "code_revision": (
            "48eb44f1c4be87cc65a98bff985a26976841e9f3"
            if is_vace
            else "29d4a35d32273d5309a3a95250bd4e118d8789b2"
        ),
        "model_revision": (
            "c76cda849bfb74d563b95f3db039421e9df2a570"
            if is_vace
            else "cb93a225fbaf1ca100f54e79da8f994995b689b3"
        ),
        "task": "animate_anything:salientbboxtrack" if is_vace else "animate-14B",
        "checkpoint_manifest_sha256": checkpoint_sha,
        "ffmpeg_sha256": ffmpeg_sha,
        "ffmpeg_version_line": "ffmpeg version qualified-build",
        "operations": (
            ["vace_performance_transfer"]
            if is_vace
            else ["animate_character", "animate_replacement"]
        ),
        "starting_frame_conditioning_verified": True,
        "reference_video_trim_verified": True,
        "constraint_plan_verified": True,
        "control_derivatives_verified": True,
        "cancellation_cleanup_verified": True,
        "minimum_free_disk_bytes": 1_000,
        "minimum_free_vram_bytes": 2_000,
    }
    report.write_text(json.dumps(payload), encoding="utf-8")
    values = _values(data_root)
    values.update(
        {
            f"{prefix}_ENABLED": "true",
            f"{prefix}_REPOSITORY_ROOT": str(repository),
            f"{prefix}_CHECKPOINT_DIR": str(checkpoint),
            f"{prefix}_PYTHON": str(Path(sys.executable).resolve()),
            f"{prefix}_QUALIFICATION_REPORT": str(report),
            f"{prefix}_CHECKPOINT_MANIFEST_SHA256": checkpoint_sha,
            "VIDEO_APP_CONTROLLED_FFMPEG_EXECUTABLE": str(ffmpeg.resolve()),
            "VIDEO_APP_CONTROLLED_FFMPEG_SHA256": ffmpeg_sha,
            "VIDEO_APP_CONTROLLED_FFMPEG_VERSION_LINE": "ffmpeg version qualified-build",
        }
    )
    return values


def _rough_cut_values(data_root: Path) -> dict[str, str]:
    executable = str(Path(sys.executable).resolve())
    report = data_root / "rough-cut-qualification.json"
    payload = {
        "status": "approved",
        "backend_revision": "ffmpeg-rough-cut-v1",
        "ffmpeg_sha256": "c" * 64,
        "ffmpeg_version_line": "ffmpeg version qualified-build",
        "ffprobe_sha256": "d" * 64,
        "ffprobe_version_line": "ffprobe version qualified-build",
        "width": 1280,
        "height": 720,
        "fps_numerator": 24,
        "fps_denominator": 1,
        "image_audio_export_verified": True,
        "measured_output_verified": True,
        "input_hash_enforcement_verified": True,
        "cancellation_cleanup_verified": True,
    }
    report.write_text(json.dumps(payload), encoding="utf-8")
    values = _values(data_root)
    values.update(
        {
            "VIDEO_APP_ROUGH_CUT_ENABLED": "true",
            "VIDEO_APP_ROUGH_CUT_QUALIFICATION_REPORT": str(report),
            "VIDEO_APP_ROUGH_CUT_FFMPEG_EXECUTABLE": executable,
            "VIDEO_APP_ROUGH_CUT_FFMPEG_SHA256": "c" * 64,
            "VIDEO_APP_ROUGH_CUT_FFMPEG_VERSION_LINE": "ffmpeg version qualified-build",
            "VIDEO_APP_FFPROBE_EXECUTABLE": executable,
            "VIDEO_APP_FFPROBE_SHA256": "d" * 64,
            "VIDEO_APP_FFPROBE_VERSION_LINE": "ffprobe version qualified-build",
            "VIDEO_APP_ROUGH_CUT_WIDTH": "1280",
            "VIDEO_APP_ROUGH_CUT_HEIGHT": "720",
            "VIDEO_APP_ROUGH_CUT_FPS_NUMERATOR": "24",
            "VIDEO_APP_ROUGH_CUT_FPS_DENOMINATOR": "1",
        }
    )
    return values


def _timeline_render_values(data_root: Path) -> dict[str, str]:
    executable = str(Path(sys.executable).resolve())
    font = data_root / "telugu.ttf"
    font.write_bytes(b"qualified Telugu font")
    report = data_root / "timeline-render-qualification.json"
    payload = {
        "status": "approved",
        "backend_revision": "ffmpeg-timeline-render-v1",
        "ffmpeg_sha256": "c" * 64,
        "ffmpeg_version_line": "ffmpeg version qualified-build",
        "ffprobe_sha256": "d" * 64,
        "ffprobe_version_line": "ffprobe version qualified-build",
        "font_sha256": "e" * 64,
        "font_family": "Noto Sans Telugu",
        "width": 1280,
        "height": 720,
        "fps_numerator": 24,
        "fps_denominator": 1,
        "duration_ms": 900_000,
        "title_caption_verified": True,
        "telugu_glyphs_verified": True,
        "audio_mix_verified": True,
        "measured_output_verified": True,
        "input_hash_enforcement_verified": True,
        "cancellation_cleanup_verified": True,
    }
    report.write_text(json.dumps(payload), encoding="utf-8")
    values = _values(data_root)
    values.update(
        {
            "VIDEO_APP_TIMELINE_RENDER_ENABLED": "true",
            "VIDEO_APP_TIMELINE_RENDER_QUALIFICATION_REPORT": str(report),
            "VIDEO_APP_TIMELINE_RENDER_FFMPEG_EXECUTABLE": executable,
            "VIDEO_APP_TIMELINE_RENDER_FFMPEG_SHA256": "c" * 64,
            "VIDEO_APP_TIMELINE_RENDER_FFMPEG_VERSION_LINE": "ffmpeg version qualified-build",
            "VIDEO_APP_TIMELINE_RENDER_FONT_FILE": str(font),
            "VIDEO_APP_TIMELINE_RENDER_FONT_SHA256": "e" * 64,
            "VIDEO_APP_TIMELINE_RENDER_FONT_FAMILY": "Noto Sans Telugu",
            "VIDEO_APP_FFPROBE_EXECUTABLE": executable,
            "VIDEO_APP_FFPROBE_SHA256": "d" * 64,
            "VIDEO_APP_FFPROBE_VERSION_LINE": "ffprobe version qualified-build",
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
        self.assertEqual(settings.owner_id, "local-owner")
        self.assertEqual(settings.max_upload_bytes, 50 * 1024 * 1024)
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

            with self.assertRaisesRegex(ValueError, "fake, wan21, wan22, vace, or wan22-animate"):
                RuntimeSettings.from_values(values)

    def test_wan22_requires_matching_explicit_qualification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            values = _wan22_values(root)
            settings = RuntimeSettings.from_values(values)

            self.assertIsNotNone(settings.wan22)
            assert settings.wan22 is not None
            self.assertEqual(settings.wan22.minimum_free_disk_bytes, 1_000)
            self.assertEqual(settings.wan22.minimum_free_vram_bytes, 2_000)

            mismatched = dict(values)
            mismatched["VIDEO_APP_WAN22_CHECKPOINT_MANIFEST_SHA256"] = "c" * 64
            with self.assertRaisesRegex(RuntimeError, "does not match"):
                RuntimeSettings.from_values(mismatched)

    def test_wan22_backend_cannot_run_without_qualification_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            values = _values(Path(directory).resolve())
            values["VIDEO_APP_BACKEND"] = "wan22"
            with self.assertRaisesRegex(RuntimeError, "must be true"):
                RuntimeSettings.from_values(values)

    def test_controlled_runtimes_require_exact_provider_specific_evidence(self) -> None:
        for provider in ("vace", "animate"):
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                values = _controlled_values(root, provider=provider)
                settings = RuntimeSettings.from_values(values)
                configured = settings.vace if provider == "vace" else settings.animate
                self.assertIsNotNone(configured)
                assert configured is not None
                self.assertEqual(configured.minimum_free_vram_bytes, 2_000)

                report_key = (
                    "VIDEO_APP_VACE_QUALIFICATION_REPORT"
                    if provider == "vace"
                    else "VIDEO_APP_WAN_ANIMATE_QUALIFICATION_REPORT"
                )
                report = Path(values[report_key])
                payload = json.loads(report.read_text(encoding="utf-8"))
                payload["constraint_plan_verified"] = False
                report.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaisesRegex(RuntimeError, "required evidence"):
                    RuntimeSettings.from_values(values)

    def test_selected_controlled_backend_cannot_bypass_enablement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            values = _values(Path(directory).resolve())
            values["VIDEO_APP_BACKEND"] = "vace"
            with self.assertRaisesRegex(RuntimeError, "VACE_ENABLED"):
                RuntimeSettings.from_values(values)

    def test_rough_cut_runtime_requires_exact_qualification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            values = _rough_cut_values(root)
            settings = RuntimeSettings.from_values(values)

            self.assertIsNotNone(settings.rough_cut)
            assert settings.rough_cut is not None
            self.assertEqual(settings.rough_cut.width, 1280)

            report = Path(values["VIDEO_APP_ROUGH_CUT_QUALIFICATION_REPORT"])
            payload = json.loads(report.read_text(encoding="utf-8"))
            payload["cancellation_cleanup_verified"] = False
            report.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "required evidence"):
                RuntimeSettings.from_values(values)

    def test_selected_rough_cut_backend_cannot_bypass_enablement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            values = _values(Path(directory).resolve())
            values["VIDEO_APP_BACKEND"] = "ffmpeg-rough-cut"
            with self.assertRaisesRegex(RuntimeError, "ROUGH_CUT_ENABLED"):
                RuntimeSettings.from_values(values)

    def test_timeline_render_runtime_requires_exact_qualification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            values = _timeline_render_values(root)
            settings = RuntimeSettings.from_values(values)

            self.assertIsNotNone(settings.timeline_render)
            assert settings.timeline_render is not None
            self.assertEqual(settings.timeline_render.duration_ms, 900_000)

            report = Path(values["VIDEO_APP_TIMELINE_RENDER_QUALIFICATION_REPORT"])
            payload = json.loads(report.read_text(encoding="utf-8"))
            payload["telugu_glyphs_verified"] = False
            report.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "required evidence"):
                RuntimeSettings.from_values(values)

    def test_selected_timeline_backend_cannot_bypass_enablement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            values = _values(Path(directory).resolve())
            values["VIDEO_APP_BACKEND"] = "ffmpeg-timeline-render"
            with self.assertRaisesRegex(RuntimeError, "TIMELINE_RENDER_ENABLED"):
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

    def test_ffprobe_pin_is_all_or_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            values = _values(Path(directory).resolve())
            values["VIDEO_APP_FFPROBE_EXECUTABLE"] = str(Path(sys.executable).resolve())
            with self.assertRaisesRegex(RuntimeError, "all VIDEO_APP_FFPROBE"):
                RuntimeSettings.from_values(values)

            values.update(
                {
                    "VIDEO_APP_FFPROBE_SHA256": "a" * 64,
                    "VIDEO_APP_FFPROBE_VERSION_LINE": "ffprobe version pinned-build",
                }
            )
            settings = RuntimeSettings.from_values(values)

        self.assertIsNotNone(settings.media)

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
