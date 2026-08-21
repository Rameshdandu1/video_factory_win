from __future__ import annotations

import unittest
from datetime import datetime, timezone

from video_app.domain.models import (
    DomainValidationError,
    GenerationMode,
    GenerationRequestDraft,
    GenerationResult,
    ModelCapability,
    Progress,
    Resolution,
    normalize_request,
)


class RequestNormalizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.capability = ModelCapability(
            model_id="wan21-t2v",
            display_name="Wan2.1 Text to Video",
            modes=frozenset({GenerationMode.TEXT_TO_VIDEO}),
            resolutions=frozenset({Resolution(832, 480)}),
            frame_counts=frozenset({81}),
        )

    def test_normalizes_prompt_and_generated_seed(self) -> None:
        request = normalize_request(
            GenerationRequestDraft(
                prompt="  rain over a neon city  ",
                model="wan21-t2v",
                width=832,
                height=480,
                frame_count=81,
            ),
            self.capability,
            lambda: 42,
        )

        self.assertEqual(request.prompt, "rain over a neon city")
        self.assertEqual(request.seed, 42)
        self.assertEqual((request.width, request.height), (832, 480))

    def test_preserves_explicit_zero_seed(self) -> None:
        request = normalize_request(
            GenerationRequestDraft(
                prompt="prompt",
                model="wan21-t2v",
                width=832,
                height=480,
                frame_count=81,
                seed=0,
            ),
            self.capability,
            lambda: 99,
        )

        self.assertEqual(request.seed, 0)

    def test_rejects_empty_or_too_long_prompt(self) -> None:
        for prompt in ("   ", "x" * 2_001):
            with self.subTest(length=len(prompt)), self.assertRaises(DomainValidationError):
                normalize_request(
                    GenerationRequestDraft(
                        prompt=prompt,
                        model="wan21-t2v",
                        width=832,
                        height=480,
                        frame_count=81,
                    ),
                    self.capability,
                    lambda: 1,
                )

    def test_rejects_unsupported_setting_combinations(self) -> None:
        invalid_drafts = (
            GenerationRequestDraft("p", "other", 832, 480, 81),
            GenerationRequestDraft("p", "wan21-t2v", 480, 832, 81),
            GenerationRequestDraft("p", "wan21-t2v", 832, 480, 80),
        )
        for draft in invalid_drafts:
            with self.subTest(draft=draft), self.assertRaises(DomainValidationError):
                normalize_request(draft, self.capability, lambda: 1)

    def test_rejects_seed_outside_signed_64_bit_range(self) -> None:
        for seed in (-(2**63) - 1, 2**63):
            with self.subTest(seed=seed), self.assertRaises(DomainValidationError):
                normalize_request(
                    GenerationRequestDraft("p", "wan21-t2v", 832, 480, 81, seed),
                    self.capability,
                    lambda: 1,
                )


class OutputValueTests(unittest.TestCase):
    def test_progress_rejects_impossible_values(self) -> None:
        with self.assertRaises(DomainValidationError):
            Progress(completed_units=2, total_units=1, stage="diffusion")

    def test_result_requires_utc_and_valid_sha256(self) -> None:
        with self.assertRaises(DomainValidationError):
            GenerationResult(
                storage_key="job/output.mp4",
                media_type="video/mp4",
                resolution=Resolution(832, 480),
                frame_count=81,
                duration_seconds=5.0,
                size_bytes=100,
                sha256="not-a-checksum",
                created_at=datetime.now(timezone.utc),
            )


if __name__ == "__main__":
    unittest.main()
