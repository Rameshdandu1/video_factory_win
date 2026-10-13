from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from video_app.domain.films import (
    AcceptanceMilestone,
    ApprovalStage,
    DialogueWorkflow,
    FilmApproval,
    FilmScene,
    FilmSceneDraft,
    FilmShot,
    FilmShotDraft,
    MilestoneEvidence,
    ReferenceWorkflow,
    SceneContinuity,
    film_acceptance_passes,
    film_continuity_boundaries,
    film_readiness,
    film_workspace_fingerprint,
    pending_visual_shot_ids,
)
from video_app.domain.models import DomainValidationError

NOW = datetime(2026, 10, 12, tzinfo=timezone.utc)


def _scene(script: str = "నమస్కారం") -> FilmScene:
    draft = FilmSceneDraft(
        0,
        "Workshop conversation",
        90_000,
        script,
        "నమస్కారం: na-ma-skaa-ram",
        SceneContinuity(
            "workshop", "warm evening", "blue shirts", "toolbox", "clean", "A left; B right"
        ),
    )
    return FilmScene("scene_one", "project_one", "owner", 1, draft, draft.fingerprint(), NOW, NOW)


def _shot(shot_id: str, position: int) -> FilmShot:
    draft = FilmShotDraft(
        position,
        10_000,
        f"Independent shot {position}",
        ReferenceWorkflow.REFERENCE_GENERATION,
        ("asset_character",),
        dialogue_workflow=DialogueWorkflow.RECORDED,
        storyboard_asset_id="asset_storyboard",
        recorded_dialogue_asset_id="asset_telugu_audio",
    )
    return FilmShot(
        shot_id, "scene_one", "project_one", "owner", 1, draft, draft.fingerprint(), NOW, NOW
    )


def test_correcting_one_scene_or_shot_preserves_unrelated_fingerprints() -> None:
    scene = _scene()
    second_scene_draft = replace(
        scene.draft,
        position=1,
        title="Unrelated scene",
        telugu_script="మరొక పంక్తి",
    )
    second_scene = FilmScene(
        "scene_two",
        "project_one",
        "owner",
        1,
        second_scene_draft,
        second_scene_draft.fingerprint(),
        NOW,
        NOW,
    )
    first = _shot("shot_one", 0)
    second = _shot("shot_two", 1)

    corrected_scene = scene.revise(
        replace(scene.draft, telugu_script="సవరించిన పంక్తి"),
        now=NOW + timedelta(seconds=1),
    )
    corrected_first = first.revise(
        FilmShotDraft(
            0,
            10_000,
            "Corrected first shot",
            ReferenceWorkflow.REFERENCE_GENERATION,
            ("asset_character",),
            dialogue_workflow=DialogueWorkflow.RECORDED,
            storyboard_asset_id="asset_storyboard",
            recorded_dialogue_asset_id="asset_telugu_audio",
        ),
        now=NOW + timedelta(seconds=1),
    )

    assert corrected_scene.content_fingerprint != scene.content_fingerprint
    assert corrected_first.content_fingerprint != first.content_fingerprint
    assert second.content_fingerprint == _shot("shot_two", 1).content_fingerprint

    script_approvals = (
        FilmApproval(
            "approval_scene_one",
            "project_one",
            "owner",
            ApprovalStage.TELUGU_SCRIPT,
            scene.content_fingerprint,
            NOW,
            scene_id=scene.id,
        ),
        FilmApproval(
            "approval_scene_two",
            "project_one",
            "owner",
            ApprovalStage.TELUGU_SCRIPT,
            second_scene.content_fingerprint,
            NOW,
            scene_id=second_scene.id,
        ),
    )
    valid_scene_approvals = {
        approval.scene_id
        for approval in script_approvals
        for current in (corrected_scene, second_scene)
        if approval.scene_id == current.id
        and approval.subject_fingerprint == current.content_fingerprint
    }
    assert valid_scene_approvals == {second_scene.id}


def test_restart_resume_schedules_only_unapproved_or_changed_shots() -> None:
    first = _shot("shot_one", 0)
    second = _shot("shot_two", 1)
    approvals = (
        FilmApproval(
            "approval_one",
            "project_one",
            "owner",
            ApprovalStage.VISUAL_PERFORMANCE,
            first.content_fingerprint,
            NOW,
            scene_id="scene_one",
            shot_id=first.id,
            evidence_asset_id="asset_output_one",
        ),
        FilmApproval(
            "approval_two",
            "project_one",
            "owner",
            ApprovalStage.VISUAL_PERFORMANCE,
            second.content_fingerprint,
            NOW,
            scene_id="scene_one",
            shot_id=second.id,
            evidence_asset_id="asset_output_two",
        ),
    )

    assert pending_visual_shot_ids((first, second), approvals) == ()
    changed_first = first.revise(
        replace(first.draft, description="Replacement first shot"),
        now=NOW + timedelta(seconds=1),
    )
    assert pending_visual_shot_ids((changed_first, second), approvals) == ("shot_one",)


def test_900_second_duration_alone_never_passes_film_acceptance() -> None:
    only_final = MilestoneEvidence(
        AcceptanceMilestone.FILM_900_SECONDS, 900_000, True, "asset_900s"
    )
    assert not film_acceptance_passes((only_final,), frozenset())

    milestones = (
        MilestoneEvidence(AcceptanceMilestone.DIALOGUE_90_SECONDS, 90_000, True, "asset_90s"),
        MilestoneEvidence(AcceptanceMilestone.SEQUENCE_180_SECONDS, 180_000, True, "asset_180s"),
        only_final,
    )
    approvals = frozenset(
        {
            ApprovalStage.CHARACTER_REFERENCES,
            ApprovalStage.IDENTITY_WORKFLOW,
            ApprovalStage.TELUGU_SCRIPT,
            ApprovalStage.PRONUNCIATION,
            ApprovalStage.VOICE_PERFORMANCE,
            ApprovalStage.STORYBOARD,
            ApprovalStage.VISUAL_PERFORMANCE,
            ApprovalStage.LIP_SYNC,
            ApprovalStage.ADJACENT_SHOT_CONTINUITY,
            ApprovalStage.ROUGH_CUT,
            ApprovalStage.FINAL_SOUND_MIX,
        }
    )
    assert film_acceptance_passes(milestones, approvals)

    out_of_order = (milestones[1], milestones[0], milestones[2])
    assert not film_acceptance_passes(out_of_order, approvals)


def test_recorded_dialogue_and_tts_are_explicit_equal_workflows() -> None:
    recorded = _shot("shot_recorded", 0)
    assert recorded.draft.dialogue_workflow is DialogueWorkflow.RECORDED

    tts_draft = replace(
        recorded.draft,
        dialogue_workflow=DialogueWorkflow.TTS,
        recorded_dialogue_asset_id=None,
    )
    assert tts_draft.fingerprint() != recorded.content_fingerprint

    with pytest.raises(DomainValidationError):
        replace(recorded.draft, dialogue_workflow=DialogueWorkflow.TTS).fingerprint()


def test_house_to_temple_readiness_is_derived_and_preserves_unrelated_approvals() -> None:
    house_draft = replace(_scene().draft, target_duration_ms=450_000)
    temple_draft = replace(
        house_draft,
        position=1,
        title="Temple conversation",
        telugu_script="దేవాలయంలో సంభాషణ",
        continuity=SceneContinuity(
            "temple",
            "oil lamps",
            "white festival clothes",
            "flower basket",
            "rain-soaked",
            "A foreground; B at doorway",
        ),
    )
    house = FilmScene(
        "scene_house",
        "project_one",
        "owner",
        1,
        house_draft,
        house_draft.fingerprint(),
        NOW,
        NOW,
    )
    temple = FilmScene(
        "scene_temple",
        "project_one",
        "owner",
        1,
        temple_draft,
        temple_draft.fingerprint(),
        NOW,
        NOW,
    )
    house_shot_draft = replace(_shot("shot_house", 0).draft, target_duration_ms=450_000)
    house_shot = FilmShot(
        "shot_house",
        house.id,
        "project_one",
        "owner",
        1,
        house_shot_draft,
        house_shot_draft.fingerprint(),
        NOW,
        NOW,
    )
    temple_shot_draft = replace(_shot("shot_temple", 0).draft, target_duration_ms=450_000)
    temple_shot = FilmShot(
        "shot_temple",
        temple.id,
        "project_one",
        "owner",
        1,
        temple_shot_draft,
        temple_shot_draft.fingerprint(),
        NOW,
        NOW,
    )
    approvals: list[FilmApproval] = []
    for scene in (house, temple):
        for stage in (ApprovalStage.TELUGU_SCRIPT, ApprovalStage.PRONUNCIATION):
            approvals.append(
                FilmApproval(
                    f"{scene.id}-{stage.value}",
                    "project_one",
                    "owner",
                    stage,
                    scene.content_fingerprint,
                    NOW,
                    scene_id=scene.id,
                )
            )
    for shot in (house_shot, temple_shot):
        for stage in (
            ApprovalStage.CHARACTER_REFERENCES,
            ApprovalStage.IDENTITY_WORKFLOW,
            ApprovalStage.VOICE_PERFORMANCE,
            ApprovalStage.STORYBOARD,
            ApprovalStage.VISUAL_PERFORMANCE,
            ApprovalStage.LIP_SYNC,
        ):
            approvals.append(
                FilmApproval(
                    f"{shot.id}-{stage.value}",
                    "project_one",
                    "owner",
                    stage,
                    shot.content_fingerprint,
                    NOW,
                    scene_id=shot.scene_id,
                    shot_id=shot.id,
                    evidence_asset_id="reviewed_media",
                )
            )

    boundaries = film_continuity_boundaries((house, temple), (temple_shot, house_shot))
    assert len(boundaries) == 1
    assert boundaries[0].left_shot_id == "shot_house"
    assert boundaries[0].right_shot_id == "shot_temple"
    assert boundaries[0].changed_fields == (
        "location",
        "lighting",
        "wardrobe",
        "props",
        "physical_state",
        "character_positions",
    )

    readiness = film_readiness(
        (house, temple),
        (house_shot, temple_shot),
        tuple(approvals),
        project_contract_fingerprint="c" * 64,
        target_duration_ms=900_000,
    )
    assert readiness.structural_blockers == ()
    assert readiness.ready_for_rough_cut
    assert readiness.next_gate is ApprovalStage.ROUGH_CUT

    changed_house_shot = house_shot.revise(
        replace(house_shot.draft, description="Corrected house performance"),
        now=NOW + timedelta(seconds=1),
    )
    resumed = film_readiness(
        (house, temple),
        (changed_house_shot, temple_shot),
        tuple(approvals),
        project_contract_fingerprint="c" * 64,
        target_duration_ms=900_000,
    )
    pending_shots = {item.shot_id for item in resumed.pending_approvals if item.shot_id is not None}
    assert pending_shots == {"shot_house"}
    assert "shot_temple" not in pending_shots
    assert resumed.workspace_fingerprint == film_workspace_fingerprint(
        (house, temple), (changed_house_shot, temple_shot), "c" * 64
    )
