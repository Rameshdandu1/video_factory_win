"""HTTP models for the Telugu short-film workflow."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from video_app.application.films import FilmWorkspace
from video_app.domain.films import (
    ApprovalStage,
    ContinuityBoundary,
    DialogueWorkflow,
    FilmApproval,
    FilmReadiness,
    FilmReadinessRequirement,
    FilmScene,
    FilmSceneDraft,
    FilmShot,
    FilmShotDraft,
    ReferenceWorkflow,
    SceneContinuity,
)


class SceneContinuityModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    location: str = Field(min_length=1, max_length=1_000)
    lighting: str = Field(min_length=1, max_length=1_000)
    wardrobe: str = Field(min_length=1, max_length=1_000)
    props: str = Field(min_length=1, max_length=1_000)
    physical_state: str = Field(min_length=1, max_length=1_000)
    character_positions: str = Field(min_length=1, max_length=1_000)


class FilmSceneSaveModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str | None = None
    expected_version: int | None = Field(default=None, ge=1, strict=True)
    position: int = Field(ge=0, le=1_000, strict=True)
    title: str = Field(min_length=1, max_length=200)
    target_duration_ms: int = Field(gt=0, le=900_000, strict=True)
    telugu_script: str = Field(min_length=1, max_length=20_000)
    pronunciation_notes: str = Field(min_length=1, max_length=10_000)
    continuity: SceneContinuityModel

    def to_domain(self) -> FilmSceneDraft:
        return FilmSceneDraft(
            position=self.position,
            title=self.title,
            target_duration_ms=self.target_duration_ms,
            telugu_script=self.telugu_script,
            pronunciation_notes=self.pronunciation_notes,
            continuity=SceneContinuity(**self.continuity.model_dump()),
        )


class FilmShotSaveModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str | None = None
    expected_version: int | None = Field(default=None, ge=1, strict=True)
    scene_id: str = Field(min_length=1, max_length=100)
    position: int = Field(ge=0, le=10_000, strict=True)
    target_duration_ms: int = Field(gt=0, le=900_000, strict=True)
    description: str = Field(min_length=1, max_length=2_000)
    reference_workflow: ReferenceWorkflow
    character_reference_asset_ids: tuple[str, ...] = Field(default=(), max_length=20)
    dialogue_workflow: DialogueWorkflow
    storyboard_asset_id: str = Field(min_length=1, max_length=100)
    source_footage_asset_id: str | None = None
    recorded_dialogue_asset_id: str | None = None

    def to_domain(self) -> FilmShotDraft:
        return FilmShotDraft(
            position=self.position,
            target_duration_ms=self.target_duration_ms,
            description=self.description,
            reference_workflow=self.reference_workflow,
            character_reference_asset_ids=self.character_reference_asset_ids,
            dialogue_workflow=self.dialogue_workflow,
            storyboard_asset_id=self.storyboard_asset_id,
            source_footage_asset_id=self.source_footage_asset_id,
            recorded_dialogue_asset_id=self.recorded_dialogue_asset_id,
        )


class FilmApprovalRequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stage: ApprovalStage
    scene_id: str | None = None
    shot_id: str | None = None
    evidence_asset_id: str | None = None


class FilmSceneModel(BaseModel):
    id: str
    version: int
    content_fingerprint: str
    created_at: datetime
    updated_at: datetime
    draft: FilmSceneSaveModel

    @classmethod
    def from_domain(cls, scene: FilmScene) -> FilmSceneModel:
        return cls(
            id=scene.id,
            version=scene.version,
            content_fingerprint=scene.content_fingerprint,
            created_at=scene.created_at,
            updated_at=scene.updated_at,
            draft=FilmSceneSaveModel(
                position=scene.draft.position,
                title=scene.draft.title,
                target_duration_ms=scene.draft.target_duration_ms,
                telugu_script=scene.draft.telugu_script,
                pronunciation_notes=scene.draft.pronunciation_notes,
                continuity=SceneContinuityModel(
                    location=scene.draft.continuity.location,
                    lighting=scene.draft.continuity.lighting,
                    wardrobe=scene.draft.continuity.wardrobe,
                    props=scene.draft.continuity.props,
                    physical_state=scene.draft.continuity.physical_state,
                    character_positions=scene.draft.continuity.character_positions,
                ),
            ),
        )


class FilmShotModel(BaseModel):
    id: str
    scene_id: str
    version: int
    content_fingerprint: str
    created_at: datetime
    updated_at: datetime
    draft: FilmShotSaveModel

    @classmethod
    def from_domain(cls, shot: FilmShot) -> FilmShotModel:
        return cls(
            id=shot.id,
            scene_id=shot.scene_id,
            version=shot.version,
            content_fingerprint=shot.content_fingerprint,
            created_at=shot.created_at,
            updated_at=shot.updated_at,
            draft=FilmShotSaveModel(
                scene_id=shot.scene_id,
                position=shot.draft.position,
                target_duration_ms=shot.draft.target_duration_ms,
                description=shot.draft.description,
                reference_workflow=shot.draft.reference_workflow,
                character_reference_asset_ids=shot.draft.character_reference_asset_ids,
                dialogue_workflow=shot.draft.dialogue_workflow,
                storyboard_asset_id=shot.draft.storyboard_asset_id,
                source_footage_asset_id=shot.draft.source_footage_asset_id,
                recorded_dialogue_asset_id=shot.draft.recorded_dialogue_asset_id,
            ),
        )


class FilmApprovalModel(BaseModel):
    id: str
    stage: ApprovalStage
    subject_fingerprint: str
    approved_at: datetime
    scene_id: str | None
    shot_id: str | None
    evidence_asset_id: str | None

    @classmethod
    def from_domain(cls, approval: FilmApproval) -> FilmApprovalModel:
        return cls(
            id=approval.id,
            stage=approval.stage,
            subject_fingerprint=approval.subject_fingerprint,
            approved_at=approval.approved_at,
            scene_id=approval.scene_id,
            shot_id=approval.shot_id,
            evidence_asset_id=approval.evidence_asset_id,
        )


class FilmWorkspaceModel(BaseModel):
    scenes: tuple[FilmSceneModel, ...]
    shots: tuple[FilmShotModel, ...]
    approvals: tuple[FilmApprovalModel, ...]

    @classmethod
    def from_domain(cls, workspace: FilmWorkspace) -> FilmWorkspaceModel:
        return cls(
            scenes=tuple(FilmSceneModel.from_domain(item) for item in workspace.scenes),
            shots=tuple(FilmShotModel.from_domain(item) for item in workspace.shots),
            approvals=tuple(FilmApprovalModel.from_domain(item) for item in workspace.approvals),
        )


class ContinuityBoundaryModel(BaseModel):
    position: int
    left_scene_id: str
    left_shot_id: str
    right_scene_id: str
    right_shot_id: str
    fingerprint: str
    cross_scene: bool
    changed_fields: tuple[str, ...]

    @classmethod
    def from_domain(cls, boundary: ContinuityBoundary) -> ContinuityBoundaryModel:
        return cls(
            position=boundary.position,
            left_scene_id=boundary.left_scene_id,
            left_shot_id=boundary.left_shot_id,
            right_scene_id=boundary.right_scene_id,
            right_shot_id=boundary.right_shot_id,
            fingerprint=boundary.fingerprint,
            cross_scene=boundary.cross_scene,
            changed_fields=boundary.changed_fields,
        )


class FilmReadinessRequirementModel(BaseModel):
    stage: ApprovalStage
    message: str
    scene_id: str | None
    shot_id: str | None

    @classmethod
    def from_domain(cls, requirement: FilmReadinessRequirement) -> FilmReadinessRequirementModel:
        return cls(
            stage=requirement.stage,
            message=requirement.message,
            scene_id=requirement.scene_id,
            shot_id=requirement.shot_id,
        )


class FilmReadinessModel(BaseModel):
    workspace_fingerprint: str
    continuity_boundaries: tuple[ContinuityBoundaryModel, ...]
    structural_blockers: tuple[str, ...]
    pending_approvals: tuple[FilmReadinessRequirementModel, ...]
    ready_for_rough_cut: bool
    ready_for_final_footage: bool
    ready_for_dialogue_90_seconds: bool
    ready_for_sequence_180_seconds: bool
    ready_for_film_900_seconds: bool
    ready_for_final_sound: bool
    accepted: bool
    next_gate: ApprovalStage | None

    @classmethod
    def from_domain(cls, readiness: FilmReadiness) -> FilmReadinessModel:
        return cls(
            workspace_fingerprint=readiness.workspace_fingerprint,
            continuity_boundaries=tuple(
                ContinuityBoundaryModel.from_domain(item)
                for item in readiness.continuity_boundaries
            ),
            structural_blockers=readiness.structural_blockers,
            pending_approvals=tuple(
                FilmReadinessRequirementModel.from_domain(item)
                for item in readiness.pending_approvals
            ),
            ready_for_rough_cut=readiness.ready_for_rough_cut,
            ready_for_final_footage=readiness.ready_for_final_footage,
            ready_for_dialogue_90_seconds=readiness.ready_for_dialogue_90_seconds,
            ready_for_sequence_180_seconds=readiness.ready_for_sequence_180_seconds,
            ready_for_film_900_seconds=readiness.ready_for_film_900_seconds,
            ready_for_final_sound=readiness.ready_for_final_sound,
            accepted=readiness.accepted,
            next_gate=readiness.next_gate,
        )
