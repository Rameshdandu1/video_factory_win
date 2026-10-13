from __future__ import annotations

import unittest

from pydantic import ValidationError

from video_app.api.image_models import ControlledGenerationDraftModel, ImageGenerationDraftModel
from video_app.api.models import GenerationRequestModel
from video_app.domain.models import GenerationMode


class ImageTransportModelTests(unittest.TestCase):
    def test_v2_seed_is_a_lossless_signed_64_bit_string(self) -> None:
        lower = ImageGenerationDraftModel(
            prompt="prompt",
            idempotency_key="request-lower",
            seed=str(-(2**63)),
        )
        upper = ImageGenerationDraftModel(
            prompt="prompt",
            idempotency_key="request-upper",
            seed=str(2**63 - 1),
        )
        self.assertEqual(lower.to_domain().seed, -(2**63))
        self.assertEqual(upper.to_domain().seed, 2**63 - 1)
        for invalid in (str(-(2**63) - 1), str(2**63), "1.0", "+1"):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                ImageGenerationDraftModel(prompt="prompt", idempotency_key="request", seed=invalid)

    def test_v1_contract_does_not_accept_image_to_video(self) -> None:
        with self.assertRaises(ValidationError):
            GenerationRequestModel(
                mode=GenerationMode.IMAGE_TO_VIDEO,
                prompt="prompt",
                model="wan22-ti2v-5b",
                width=1280,
                height=704,
                frame_count=81,
                seed=1,
            )

    def test_controlled_submission_keeps_provider_and_environment_choice_explicit(self) -> None:
        model = ControlledGenerationDraftModel(
            provider_id="vace-performance-transfer",
            preserve_environment=True,
            prompt="performance",
            idempotency_key="shot-one-vace-one",
            seed="-7",
        )

        draft = model.to_controlled_domain()

        self.assertEqual(draft.provider_id, "vace-performance-transfer")
        self.assertTrue(draft.preserve_environment)
        self.assertEqual(draft.seed, -7)


if __name__ == "__main__":
    unittest.main()
