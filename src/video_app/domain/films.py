"""Telugu short-film planning, continuity, approval, and acceptance contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from itertools import pairwise

from video_app.domain.models import DomainValidationError, _require_non_empty, _require_utc_aware


class ReferenceWorkflow(str, Enum):
    REFERENCE_GENERATION = "reference_generation"
    APPROVED_SOURCE_FOOTAGE = "approved_source_footage"


class DialogueWorkflow(str, Enum):
    TTS = "tts"
    RECORDED = "recorded"


class ApprovalStage(str, Enum):
    CHARACTER_REFERENCES = "character_references"
    IDENTITY_WORKFLOW = "identity_workflow"
    TELUGU_SCRIPT = "telugu_script"
    PRONUNCIATION = "pronunciation"
    VOICE_PERFORMANCE = "voice_performance"
    STORYBOARD = "storyboard"
    VISUAL_PERFORMANCE = "visual_performance"
    LIP_SYNC = "lip_sync"
    ADJACENT_SHOT_CONTINUITY = "adjacent_shot_continuity"
    ROUGH_CUT = "rough_cut"
    DIALOGUE_90_SECONDS = "dialogue_90_seconds"
    SEQUENCE_180_SECONDS = "sequence_180_seconds"
    FILM_900_SECONDS = "film_900_seconds"
    FINAL_SOUND_MIX = "final_sound_mix"


class AcceptanceMilestone(str, Enum):
    DIALOGUE_90_SECONDS = "dialogue_90_seconds"
    SEQUENCE_180_SECONDS = "sequence_180_seconds"
    FILM_900_SECONDS = "film_900_seconds"


@dataclass(frozen=True, slots=True)
class SceneContinuity:
    location: str
    lighting: str
    wardrobe: str
    props: str
    physical_state: str
    character_positions: str

    def __post_init__(self) -> None:
        for value, field in (
            (self.location, "location"),
            (self.lighting, "lighting"),
            (self.wardrobe, "wardrobe"),
            (self.props, "props"),
            (self.physical_state, "physical state"),
            (self.character_positions, "character positions"),
        ):
            _require_non_empty(value, field)
            if len(value) > 1_000:
                raise DomainValidationError(f"{field} is too long")


def _fingerprint(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class FilmSceneDraft:
    position: int
    title: str
    target_duration_ms: int
    telugu_script: str
    pronunciation_notes: str
    continuity: SceneContinuity

    def fingerprint(self) -> str:
        if self.position < 0 or self.target_duration_ms <= 0:
            raise DomainValidationError("scene position and duration are invalid")
        _require_non_empty(self.title, "scene title")
        _require_non_empty(self.telugu_script, "Telugu script")
        _require_non_empty(self.pronunciation_notes, "pronunciation notes")
        return _fingerprint(
            {
                "position": self.position,
                "title": self.title.strip(),
                "target_duration_ms": self.target_duration_ms,
                "telugu_script": self.telugu_script.strip(),
                "pronunciation_notes": self.pronunciation_notes.strip(),
                "continuity": {
                    "location": self.continuity.location.strip(),
                    "lighting": self.continuity.lighting.strip(),
                    "wardrobe": self.continuity.wardrobe.strip(),
                    "props": self.continuity.props.strip(),
                    "physical_state": self.continuity.physical_state.strip(),
                    "character_positions": self.continuity.character_positions.strip(),
                },
            }
        )


@dataclass(frozen=True, slots=True)
class FilmScene:
    id: str
    project_id: str
    owner_id: str
    version: int
    draft: FilmSceneDraft
    content_fingerprint: str
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if self.version < 1 or self.draft.fingerprint() != self.content_fingerprint:
            raise DomainValidationError("scene version or fingerprint is invalid")
        for value, field in (
            (self.id, "scene id"),
            (self.project_id, "project id"),
            (self.owner_id, "owner id"),
        ):
            _require_non_empty(value, field)
        _require_utc_aware(self.created_at, "created_at")
        _require_utc_aware(self.updated_at, "updated_at")

    def revise(self, draft: FilmSceneDraft, *, now: datetime) -> FilmScene:
        return replace(
            self,
            version=self.version + 1,
            draft=draft,
            content_fingerprint=draft.fingerprint(),
            updated_at=now,
        )


@dataclass(frozen=True, slots=True)
class FilmShotDraft:
    position: int
    target_duration_ms: int
    description: str
    reference_workflow: ReferenceWorkflow
    character_reference_asset_ids: tuple[str, ...]
    storyboard_asset_id: str
    dialogue_workflow: DialogueWorkflow = DialogueWorkflow.TTS
    source_footage_asset_id: str | None = None
    recorded_dialogue_asset_id: str | None = None

    def fingerprint(self) -> str:
        if self.position < 0 or self.target_duration_ms <= 0:
            raise DomainValidationError("shot position and duration are invalid")
        _require_non_empty(self.description, "shot description")
        if not self.character_reference_asset_ids:
            raise DomainValidationError("shots require approved character references")
        _require_non_empty(self.storyboard_asset_id, "storyboard asset id")
        if self.reference_workflow is ReferenceWorkflow.REFERENCE_GENERATION:
            if self.source_footage_asset_id is not None:
                raise DomainValidationError(
                    "reference generation requires character references only"
                )
        elif self.source_footage_asset_id is None:
            raise DomainValidationError("approved source-footage workflow requires source footage")
        if self.dialogue_workflow is DialogueWorkflow.RECORDED:
            if self.recorded_dialogue_asset_id is None:
                raise DomainValidationError("recorded dialogue requires an audio asset")
        elif self.recorded_dialogue_asset_id is not None:
            raise DomainValidationError("TTS dialogue must not include a recorded audio asset")
        return _fingerprint(
            {
                "position": self.position,
                "target_duration_ms": self.target_duration_ms,
                "description": self.description.strip(),
                "reference_workflow": self.reference_workflow.value,
                "character_reference_asset_ids": sorted(self.character_reference_asset_ids),
                "dialogue_workflow": self.dialogue_workflow.value,
                "storyboard_asset_id": self.storyboard_asset_id,
                "source_footage_asset_id": self.source_footage_asset_id,
                "recorded_dialogue_asset_id": self.recorded_dialogue_asset_id,
            }
        )


@dataclass(frozen=True, slots=True)
class FilmShot:
    id: str
    scene_id: str
    project_id: str
    owner_id: str
    version: int
    draft: FilmShotDraft
    content_fingerprint: str
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if self.version < 1 or self.draft.fingerprint() != self.content_fingerprint:
            raise DomainValidationError("shot version or fingerprint is invalid")
        for value, field in (
            (self.id, "shot id"),
            (self.scene_id, "scene id"),
            (self.project_id, "project id"),
            (self.owner_id, "owner id"),
        ):
            _require_non_empty(value, field)
        _require_utc_aware(self.created_at, "created_at")
        _require_utc_aware(self.updated_at, "updated_at")

    def revise(self, draft: FilmShotDraft, *, now: datetime) -> FilmShot:
        return replace(
            self,
            version=self.version + 1,
            draft=draft,
            content_fingerprint=draft.fingerprint(),
            updated_at=now,
        )


@dataclass(frozen=True, slots=True)
class FilmApproval:
    id: str
    project_id: str
    owner_id: str
    stage: ApprovalStage
    subject_fingerprint: str
    approved_at: datetime
    scene_id: str | None = None
    shot_id: str | None = None
    evidence_asset_id: str | None = None

    def __post_init__(self) -> None:
        for value, field in (
            (self.id, "approval id"),
            (self.project_id, "project id"),
            (self.owner_id, "owner id"),
        ):
            _require_non_empty(value, field)
        if len(self.subject_fingerprint) != 64 and not self.subject_fingerprint.startswith(
            "project:"
        ):
            raise DomainValidationError("approval subject fingerprint is invalid")
        _require_utc_aware(self.approved_at, "approved_at")


@dataclass(frozen=True, slots=True)
class ContinuityBoundary:
    """One deterministic review boundary between consecutive current shots."""

    position: int
    left_scene_id: str
    left_shot_id: str
    right_scene_id: str
    right_shot_id: str
    fingerprint: str
    cross_scene: bool
    changed_fields: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.position < 0:
            raise DomainValidationError("continuity boundary position is invalid")
        for value, field in (
            (self.left_scene_id, "left scene id"),
            (self.left_shot_id, "left shot id"),
            (self.right_scene_id, "right scene id"),
            (self.right_shot_id, "right shot id"),
        ):
            _require_non_empty(value, field)
        if len(self.fingerprint) != 64:
            raise DomainValidationError("continuity boundary fingerprint is invalid")


@dataclass(frozen=True, slots=True)
class FilmReadinessRequirement:
    stage: ApprovalStage
    message: str
    scene_id: str | None = None
    shot_id: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.message, "readiness requirement message")


@dataclass(frozen=True, slots=True)
class FilmReadiness:
    """Read-only projection of the current edit and its fingerprint-bound approvals."""

    workspace_fingerprint: str
    continuity_boundaries: tuple[ContinuityBoundary, ...]
    structural_blockers: tuple[str, ...]
    pending_approvals: tuple[FilmReadinessRequirement, ...]
    ready_for_rough_cut: bool
    ready_for_final_footage: bool
    ready_for_dialogue_90_seconds: bool
    ready_for_sequence_180_seconds: bool
    ready_for_film_900_seconds: bool
    ready_for_final_sound: bool
    accepted: bool
    next_gate: ApprovalStage | None

    def __post_init__(self) -> None:
        if len(self.workspace_fingerprint) != 64:
            raise DomainValidationError("film readiness fingerprint is invalid")


@dataclass(frozen=True, slots=True)
class MilestoneEvidence:
    milestone: AcceptanceMilestone
    reviewed_duration_ms: int
    real_media_reviewed: bool
    evidence_asset_id: str

    def validate(self) -> None:
        required = {
            AcceptanceMilestone.DIALOGUE_90_SECONDS: 90_000,
            AcceptanceMilestone.SEQUENCE_180_SECONDS: 180_000,
            AcceptanceMilestone.FILM_900_SECONDS: 900_000,
        }[self.milestone]
        if self.reviewed_duration_ms < required or not self.real_media_reviewed:
            raise DomainValidationError(
                "milestone requires reviewed real media at its target duration"
            )
        _require_non_empty(self.evidence_asset_id, "milestone evidence asset")


def film_acceptance_passes(
    milestones: tuple[MilestoneEvidence, ...], approvals: frozenset[ApprovalStage]
) -> bool:
    try:
        for item in milestones:
            item.validate()
    except DomainValidationError:
        return False
    required_order = tuple(AcceptanceMilestone)
    required_approvals = {
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
    return tuple(
        item.milestone for item in milestones
    ) == required_order and required_approvals.issubset(approvals)


def pending_visual_shot_ids(
    shots: tuple[FilmShot, ...], approvals: tuple[FilmApproval, ...]
) -> tuple[str, ...]:
    approved = {
        (item.shot_id, item.subject_fingerprint)
        for item in approvals
        if item.stage is ApprovalStage.VISUAL_PERFORMANCE
    }
    return tuple(shot.id for shot in shots if (shot.id, shot.content_fingerprint) not in approved)


_CONTINUITY_FIELDS = (
    "location",
    "lighting",
    "wardrobe",
    "props",
    "physical_state",
    "character_positions",
)


def film_continuity_boundaries(
    scenes: tuple[FilmScene, ...], shots: tuple[FilmShot, ...]
) -> tuple[ContinuityBoundary, ...]:
    """Return all current adjacent-shot boundaries in deterministic film order."""

    scenes_by_id = {scene.id: scene for scene in scenes}
    ordered_scenes = sorted(scenes, key=lambda item: (item.draft.position, item.id))
    ordered_shots = tuple(
        shot
        for scene in ordered_scenes
        for shot in sorted(
            (item for item in shots if item.scene_id == scene.id),
            key=lambda item: (item.draft.position, item.id),
        )
    )
    boundaries: list[ContinuityBoundary] = []
    for position, (left, right) in enumerate(pairwise(ordered_shots)):
        left_scene = scenes_by_id[left.scene_id]
        right_scene = scenes_by_id[right.scene_id]
        cross_scene = left.scene_id != right.scene_id
        changed_fields = tuple(
            field
            for field in _CONTINUITY_FIELDS
            if cross_scene
            and getattr(left_scene.draft.continuity, field).strip()
            != getattr(right_scene.draft.continuity, field).strip()
        )
        fingerprint = _fingerprint(
            {
                "position": position,
                "left_scene": (left.scene_id, left_scene.content_fingerprint),
                "left_shot": (left.id, left.content_fingerprint),
                "right_scene": (right.scene_id, right_scene.content_fingerprint),
                "right_shot": (right.id, right.content_fingerprint),
                "changed_fields": changed_fields,
            }
        )
        boundaries.append(
            ContinuityBoundary(
                position=position,
                left_scene_id=left.scene_id,
                left_shot_id=left.id,
                right_scene_id=right.scene_id,
                right_shot_id=right.id,
                fingerprint=fingerprint,
                cross_scene=cross_scene,
                changed_fields=changed_fields,
            )
        )
    return tuple(boundaries)


def film_readiness(
    scenes: tuple[FilmScene, ...],
    shots: tuple[FilmShot, ...],
    approvals: tuple[FilmApproval, ...],
    *,
    project_contract_fingerprint: str,
    target_duration_ms: int,
) -> FilmReadiness:
    """Derive current film gates without introducing mutable workflow state."""

    workspace_fingerprint = film_workspace_fingerprint(scenes, shots, project_contract_fingerprint)

    def is_current(
        stage: ApprovalStage,
        fingerprint: str,
        *,
        scene_id: str | None = None,
        shot_id: str | None = None,
    ) -> bool:
        return any(
            item.stage is stage
            and item.subject_fingerprint == fingerprint
            and item.scene_id == scene_id
            and item.shot_id == shot_id
            for item in approvals
        )

    ordered_scenes = tuple(sorted(scenes, key=lambda item: (item.draft.position, item.id)))
    scene_positions = tuple(item.draft.position for item in ordered_scenes)
    structural_blockers: list[str] = []
    if not ordered_scenes:
        structural_blockers.append("Add at least one scene.")
    if not shots:
        structural_blockers.append("Add at least one shot.")
    if len(set(scene_positions)) != len(scene_positions):
        structural_blockers.append("Scene positions must be unique.")
    if sum(scene.draft.target_duration_ms for scene in scenes) != target_duration_ms:
        structural_blockers.append("Scene durations must equal the project target.")
    for scene in ordered_scenes:
        scene_shots = tuple(item for item in shots if item.scene_id == scene.id)
        positions = tuple(item.draft.position for item in scene_shots)
        if not scene_shots:
            structural_blockers.append(f"Scene {scene.id} requires at least one shot.")
        elif len(set(positions)) != len(positions):
            structural_blockers.append(f"Shot positions in scene {scene.id} must be unique.")
        shot_duration_ms = sum(item.draft.target_duration_ms for item in scene_shots)
        if shot_duration_ms != scene.draft.target_duration_ms:
            structural_blockers.append(
                f"Shot durations in scene {scene.id} must equal the scene target."
            )

    pending: list[FilmReadinessRequirement] = []

    def require(
        stage: ApprovalStage,
        fingerprint: str,
        message: str,
        *,
        scene_id: str | None = None,
        shot_id: str | None = None,
    ) -> bool:
        current = is_current(stage, fingerprint, scene_id=scene_id, shot_id=shot_id)
        if not current:
            pending.append(FilmReadinessRequirement(stage, message, scene_id, shot_id))
        return current

    initial_current = True
    final_shots_current = True
    for scene in ordered_scenes:
        initial_current &= require(
            ApprovalStage.TELUGU_SCRIPT,
            scene.content_fingerprint,
            "Approve the current Telugu script.",
            scene_id=scene.id,
        )
        initial_current &= require(
            ApprovalStage.PRONUNCIATION,
            scene.content_fingerprint,
            "Approve the current pronunciation review.",
            scene_id=scene.id,
        )
        for shot in sorted(
            (item for item in shots if item.scene_id == scene.id),
            key=lambda item: (item.draft.position, item.id),
        ):
            for stage, message in (
                (ApprovalStage.CHARACTER_REFERENCES, "Approve character references."),
                (ApprovalStage.IDENTITY_WORKFLOW, "Verify the identity-preserving workflow."),
                (ApprovalStage.VOICE_PERFORMANCE, "Approve Telugu voice performance."),
                (ApprovalStage.STORYBOARD, "Approve the storyboard image."),
            ):
                initial_current &= require(
                    stage,
                    shot.content_fingerprint,
                    message,
                    scene_id=scene.id,
                    shot_id=shot.id,
                )
            for stage, message in (
                (ApprovalStage.VISUAL_PERFORMANCE, "Approve visual performance."),
                (ApprovalStage.LIP_SYNC, "Approve lip-sync."),
            ):
                final_shots_current &= require(
                    stage,
                    shot.content_fingerprint,
                    message,
                    scene_id=scene.id,
                    shot_id=shot.id,
                )

    rough_cut_current = require(
        ApprovalStage.ROUGH_CUT,
        workspace_fingerprint,
        "Approve the rough film assembled from current audio and storyboards.",
    )
    continuity_current = require(
        ApprovalStage.ADJACENT_SHOT_CONTINUITY,
        workspace_fingerprint,
        "Approve every adjacent-shot continuity boundary for the current edit.",
    )
    dialogue_current = require(
        ApprovalStage.DIALOGUE_90_SECONDS,
        workspace_fingerprint,
        "Approve the real 90-second Telugu dialogue scene.",
    )
    sequence_current = require(
        ApprovalStage.SEQUENCE_180_SECONDS,
        workspace_fingerprint,
        "Approve the real three-minute sequence.",
    )
    film_current = require(
        ApprovalStage.FILM_900_SECONDS,
        workspace_fingerprint,
        "Approve the real 15-minute film after all earlier gates.",
    )
    final_sound_current = require(
        ApprovalStage.FINAL_SOUND_MIX,
        workspace_fingerprint,
        "Approve the inspected full-duration final sound mix.",
    )

    structurally_complete = not structural_blockers
    ready_for_rough_cut = structurally_complete and initial_current
    ready_for_final_footage = structurally_complete and rough_cut_current
    ready_for_dialogue = structurally_complete and rough_cut_current
    ready_for_sequence = structurally_complete and dialogue_current
    ready_for_film = (
        structurally_complete
        and dialogue_current
        and sequence_current
        and final_shots_current
        and continuity_current
    )
    ready_for_final_sound = structurally_complete and film_current
    accepted = structurally_complete and film_current and final_sound_current

    next_gate: ApprovalStage | None = None
    if structurally_complete:
        if not rough_cut_current and ready_for_rough_cut:
            next_gate = ApprovalStage.ROUGH_CUT
        elif rough_cut_current and not dialogue_current:
            next_gate = ApprovalStage.DIALOGUE_90_SECONDS
        elif dialogue_current and not sequence_current:
            next_gate = ApprovalStage.SEQUENCE_180_SECONDS
        elif sequence_current and final_shots_current and not continuity_current:
            next_gate = ApprovalStage.ADJACENT_SHOT_CONTINUITY
        elif ready_for_film and not film_current:
            next_gate = ApprovalStage.FILM_900_SECONDS
        elif film_current and not final_sound_current:
            next_gate = ApprovalStage.FINAL_SOUND_MIX

    return FilmReadiness(
        workspace_fingerprint=workspace_fingerprint,
        continuity_boundaries=film_continuity_boundaries(scenes, shots),
        structural_blockers=tuple(structural_blockers),
        pending_approvals=tuple(pending),
        ready_for_rough_cut=ready_for_rough_cut,
        ready_for_final_footage=ready_for_final_footage,
        ready_for_dialogue_90_seconds=ready_for_dialogue,
        ready_for_sequence_180_seconds=ready_for_sequence,
        ready_for_film_900_seconds=ready_for_film,
        ready_for_final_sound=ready_for_final_sound,
        accepted=accepted,
        next_gate=next_gate,
    )


def film_workspace_fingerprint(
    scenes: tuple[FilmScene, ...],
    shots: tuple[FilmShot, ...],
    project_contract_fingerprint: str,
) -> str:
    """Fingerprint the current edit without coupling acceptance to mutable row versions."""

    return _fingerprint(
        {
            "project_contract_fingerprint": project_contract_fingerprint,
            "scenes": sorted((item.id, item.content_fingerprint) for item in scenes),
            "shots": sorted((item.id, item.content_fingerprint) for item in shots),
        }
    )
