from video_app.api.film_models import FilmReadinessModel
from video_app.domain.films import (
    ApprovalStage,
    ContinuityBoundary,
    FilmReadiness,
    FilmReadinessRequirement,
)


def test_film_readiness_model_preserves_gate_and_boundary_contract() -> None:
    readiness = FilmReadiness(
        workspace_fingerprint="a" * 64,
        continuity_boundaries=(
            ContinuityBoundary(
                position=0,
                left_scene_id="scene_house",
                left_shot_id="shot_house",
                right_scene_id="scene_temple",
                right_shot_id="shot_temple",
                fingerprint="b" * 64,
                cross_scene=True,
                changed_fields=("location", "lighting"),
            ),
        ),
        structural_blockers=(),
        pending_approvals=(
            FilmReadinessRequirement(
                ApprovalStage.ROUGH_CUT,
                "Approve the current rough film.",
            ),
        ),
        ready_for_rough_cut=True,
        ready_for_final_footage=False,
        ready_for_dialogue_90_seconds=False,
        ready_for_sequence_180_seconds=False,
        ready_for_film_900_seconds=False,
        ready_for_final_sound=False,
        accepted=False,
        next_gate=ApprovalStage.ROUGH_CUT,
    )

    payload = FilmReadinessModel.from_domain(readiness).model_dump(mode="json")

    assert payload["next_gate"] == "rough_cut"
    assert payload["continuity_boundaries"][0]["left_shot_id"] == "shot_house"
    assert payload["pending_approvals"][0]["stage"] == "rough_cut"
