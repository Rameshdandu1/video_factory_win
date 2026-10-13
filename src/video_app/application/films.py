"""Telugu short-film scene, shot, and approval use cases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from video_app.application.assets import AssetRepository
from video_app.application.ports import Clock
from video_app.application.projects import ProjectRepository, ProjectRevisionConflictError
from video_app.domain.assets import AssetKind, AssetState, MediaAsset
from video_app.domain.films import (
    ApprovalStage,
    DialogueWorkflow,
    FilmApproval,
    FilmReadiness,
    FilmScene,
    FilmSceneDraft,
    FilmShot,
    FilmShotDraft,
    ReferenceWorkflow,
    film_readiness,
    film_workspace_fingerprint,
)
from video_app.domain.models import DomainValidationError
from video_app.domain.projects import Project, ProjectPreset


class FilmIdentifierFactory(Protocol):
    def new_scene_id(self) -> str: ...
    def new_shot_id(self) -> str: ...
    def new_approval_id(self) -> str: ...


class FilmSubjectNotFoundError(LookupError):
    """Raised when a scene or shot is absent from an owner-scoped film."""


@dataclass(frozen=True, slots=True)
class FilmWorkspace:
    scenes: tuple[FilmScene, ...]
    shots: tuple[FilmShot, ...]
    approvals: tuple[FilmApproval, ...]


class FilmRepository(Protocol):
    async def save_scene(
        self,
        *,
        scene_id: str,
        owner_id: str,
        project_id: str,
        draft: FilmSceneDraft,
        expected_version: int | None,
        now: datetime,
    ) -> FilmScene: ...

    async def save_shot(
        self,
        *,
        shot_id: str,
        scene_id: str,
        owner_id: str,
        project_id: str,
        draft: FilmShotDraft,
        expected_version: int | None,
        now: datetime,
    ) -> FilmShot: ...

    async def get_scene(self, owner_id: str, project_id: str, scene_id: str) -> FilmScene: ...
    async def get_shot(self, owner_id: str, project_id: str, shot_id: str) -> FilmShot: ...
    async def snapshot(self, owner_id: str, project_id: str) -> FilmWorkspace: ...
    async def add_approval(self, approval: FilmApproval) -> FilmApproval: ...


async def _require_film(projects: ProjectRepository, owner_id: str, project_id: str) -> Project:
    project = await projects.get(owner_id, project_id)
    if project.preset is not ProjectPreset.TELUGU_SHORT_FILM_900:
        raise DomainValidationError("film workflow requires the Telugu 900-second preset")
    return project


@dataclass(frozen=True, slots=True)
class SaveFilmScene:
    projects: ProjectRepository
    films: FilmRepository
    clock: Clock
    identifiers: FilmIdentifierFactory
    owner_id: str

    async def __call__(
        self,
        project_id: str,
        draft: FilmSceneDraft,
        *,
        scene_id: str | None = None,
        expected_version: int | None = None,
    ) -> FilmScene:
        await _require_film(self.projects, self.owner_id, project_id)
        draft.fingerprint()
        if (scene_id is None) != (expected_version is None):
            raise ProjectRevisionConflictError("scene identity and expected version must match")
        workspace = await self.films.snapshot(self.owner_id, project_id)
        total_duration_ms = draft.target_duration_ms + sum(
            item.draft.target_duration_ms for item in workspace.scenes if item.id != scene_id
        )
        if total_duration_ms > 900_000:
            raise DomainValidationError("film scene targets exceed 900 seconds")
        return await self.films.save_scene(
            scene_id=scene_id or self.identifiers.new_scene_id(),
            owner_id=self.owner_id,
            project_id=project_id,
            draft=draft,
            expected_version=expected_version,
            now=self.clock.now(),
        )


@dataclass(frozen=True, slots=True)
class SaveFilmShot:
    projects: ProjectRepository
    assets: AssetRepository
    films: FilmRepository
    clock: Clock
    identifiers: FilmIdentifierFactory
    owner_id: str

    async def __call__(
        self,
        project_id: str,
        scene_id: str,
        draft: FilmShotDraft,
        *,
        shot_id: str | None = None,
        expected_version: int | None = None,
    ) -> FilmShot:
        await _require_film(self.projects, self.owner_id, project_id)
        scene = await self.films.get_scene(self.owner_id, project_id, scene_id)
        draft.fingerprint()
        for asset_id in draft.character_reference_asset_ids:
            asset = await self.assets.get(self.owner_id, project_id, asset_id)
            if asset.kind is not AssetKind.IMAGE:
                raise DomainValidationError("character references must be image assets")
        storyboard = await self.assets.get(self.owner_id, project_id, draft.storyboard_asset_id)
        if storyboard.kind is not AssetKind.IMAGE:
            raise DomainValidationError("storyboard references must be image assets")
        if draft.source_footage_asset_id is not None:
            source = await self.assets.get(self.owner_id, project_id, draft.source_footage_asset_id)
            if source.kind is not AssetKind.VIDEO:
                raise DomainValidationError("source footage must be a video asset")
        if draft.dialogue_workflow is DialogueWorkflow.RECORDED:
            assert draft.recorded_dialogue_asset_id is not None
            dialogue = await self.assets.get(
                self.owner_id, project_id, draft.recorded_dialogue_asset_id
            )
            if dialogue.kind is not AssetKind.AUDIO:
                raise DomainValidationError("recorded Telugu dialogue must be an audio asset")
        if (shot_id is None) != (expected_version is None):
            raise ProjectRevisionConflictError("shot identity and expected version must match")
        workspace = await self.films.snapshot(self.owner_id, project_id)
        total_duration_ms = draft.target_duration_ms + sum(
            item.draft.target_duration_ms
            for item in workspace.shots
            if item.scene_id == scene_id and item.id != shot_id
        )
        if total_duration_ms > scene.draft.target_duration_ms:
            raise DomainValidationError("shot targets exceed their scene target")
        return await self.films.save_shot(
            shot_id=shot_id or self.identifiers.new_shot_id(),
            scene_id=scene_id,
            owner_id=self.owner_id,
            project_id=project_id,
            draft=draft,
            expected_version=expected_version,
            now=self.clock.now(),
        )


@dataclass(frozen=True, slots=True)
class GetFilmWorkspace:
    projects: ProjectRepository
    films: FilmRepository
    owner_id: str

    async def __call__(self, project_id: str) -> FilmWorkspace:
        await _require_film(self.projects, self.owner_id, project_id)
        return await self.films.snapshot(self.owner_id, project_id)


@dataclass(frozen=True, slots=True)
class GetFilmReadiness:
    projects: ProjectRepository
    films: FilmRepository
    owner_id: str

    async def __call__(self, project_id: str) -> FilmReadiness:
        project = await _require_film(self.projects, self.owner_id, project_id)
        workspace = await self.films.snapshot(self.owner_id, project_id)
        return film_readiness(
            workspace.scenes,
            workspace.shots,
            workspace.approvals,
            project_contract_fingerprint=project.film_contract_fingerprint(),
            target_duration_ms=project.target_duration_ms,
        )


@dataclass(frozen=True, slots=True)
class ApproveFilmSubject:
    projects: ProjectRepository
    assets: AssetRepository
    films: FilmRepository
    clock: Clock
    identifiers: FilmIdentifierFactory
    owner_id: str

    async def __call__(
        self,
        project_id: str,
        *,
        stage: ApprovalStage,
        scene_id: str | None,
        shot_id: str | None,
        evidence_asset_id: str | None,
    ) -> FilmApproval:
        project = await _require_film(self.projects, self.owner_id, project_id)
        scene = (
            await self.films.get_scene(self.owner_id, project_id, scene_id)
            if scene_id is not None
            else None
        )
        shot = (
            await self.films.get_shot(self.owner_id, project_id, shot_id)
            if shot_id is not None
            else None
        )
        if shot is not None and scene_id is not None and shot.scene_id != scene_id:
            raise DomainValidationError("shot does not belong to the selected scene")
        shot_stages = {
            ApprovalStage.CHARACTER_REFERENCES,
            ApprovalStage.IDENTITY_WORKFLOW,
            ApprovalStage.VOICE_PERFORMANCE,
            ApprovalStage.STORYBOARD,
            ApprovalStage.VISUAL_PERFORMANCE,
            ApprovalStage.LIP_SYNC,
        }
        scene_stages = {ApprovalStage.TELUGU_SCRIPT, ApprovalStage.PRONUNCIATION}
        project_stages = {
            ApprovalStage.ADJACENT_SHOT_CONTINUITY,
            ApprovalStage.ROUGH_CUT,
            ApprovalStage.DIALOGUE_90_SECONDS,
            ApprovalStage.SEQUENCE_180_SECONDS,
            ApprovalStage.FILM_900_SECONDS,
            ApprovalStage.FINAL_SOUND_MIX,
        }
        if stage in shot_stages and (shot is None or scene is None):
            raise DomainValidationError("this approval stage requires a scene and shot")
        if stage in scene_stages and (scene is None or shot is not None):
            raise DomainValidationError("this approval stage requires a scene")
        if stage in project_stages and (scene is not None or shot is not None):
            raise DomainValidationError("this approval stage applies to the current film edit")
        if (
            stage is ApprovalStage.CHARACTER_REFERENCES
            and shot is not None
            and not shot.draft.character_reference_asset_ids
        ):
            raise DomainValidationError("approved character references are required")
        workspace = await self.films.snapshot(self.owner_id, project_id)
        workspace_fingerprint = film_workspace_fingerprint(
            workspace.scenes,
            workspace.shots,
            project.film_contract_fingerprint(),
        )

        def approved(
            required_stage: ApprovalStage,
            fingerprint: str,
            *,
            required_scene_id: str | None = None,
            required_shot_id: str | None = None,
        ) -> bool:
            return any(
                item.stage is required_stage
                and item.subject_fingerprint == fingerprint
                and item.scene_id == required_scene_id
                and item.shot_id == required_shot_id
                for item in workspace.approvals
            )

        evidence: MediaAsset | None = None
        if evidence_asset_id is not None:
            evidence = await self.assets.get(self.owner_id, project_id, evidence_asset_id)
        evidence_stages = {
            ApprovalStage.IDENTITY_WORKFLOW,
            ApprovalStage.VOICE_PERFORMANCE,
            ApprovalStage.STORYBOARD,
            ApprovalStage.VISUAL_PERFORMANCE,
            ApprovalStage.LIP_SYNC,
            ApprovalStage.ADJACENT_SHOT_CONTINUITY,
            ApprovalStage.ROUGH_CUT,
            ApprovalStage.DIALOGUE_90_SECONDS,
            ApprovalStage.SEQUENCE_180_SECONDS,
            ApprovalStage.FILM_900_SECONDS,
            ApprovalStage.FINAL_SOUND_MIX,
        }
        if stage in evidence_stages and evidence is None:
            raise DomainValidationError("this approval requires real media evidence")
        if (
            stage is ApprovalStage.STORYBOARD
            and shot is not None
            and evidence_asset_id != shot.draft.storyboard_asset_id
        ):
            raise DomainValidationError("approve the storyboard attached to this shot")
        if (
            stage is ApprovalStage.IDENTITY_WORKFLOW
            and evidence is not None
            and evidence.kind is not AssetKind.VIDEO
        ):
            raise DomainValidationError("identity workflow evidence must be video")
        if (
            stage is ApprovalStage.IDENTITY_WORKFLOW
            and shot is not None
            and shot.draft.reference_workflow is ReferenceWorkflow.APPROVED_SOURCE_FOOTAGE
            and evidence_asset_id != shot.draft.source_footage_asset_id
        ):
            raise DomainValidationError("approve the source footage attached to this shot")
        if (
            stage is ApprovalStage.VOICE_PERFORMANCE
            and evidence is not None
            and evidence.kind not in {AssetKind.AUDIO, AssetKind.VIDEO}
        ):
            raise DomainValidationError("voice performance evidence must contain audio")
        if (
            stage is ApprovalStage.STORYBOARD
            and evidence is not None
            and evidence.kind is not AssetKind.IMAGE
        ):
            raise DomainValidationError("storyboard evidence must be an image")
        video_evidence_stages = {
            ApprovalStage.IDENTITY_WORKFLOW,
            ApprovalStage.VISUAL_PERFORMANCE,
            ApprovalStage.LIP_SYNC,
            ApprovalStage.ADJACENT_SHOT_CONTINUITY,
            ApprovalStage.ROUGH_CUT,
        }
        if (
            stage in video_evidence_stages
            and evidence is not None
            and evidence.kind is not AssetKind.VIDEO
        ):
            raise DomainValidationError("this approval requires video evidence")
        if (
            stage in video_evidence_stages
            and evidence is not None
            and evidence.state is not AssetState.INSPECTED
        ):
            raise DomainValidationError("video evidence must have verified media metadata")
        if stage is ApprovalStage.VISUAL_PERFORMANCE and shot is not None:
            if not approved(
                ApprovalStage.CHARACTER_REFERENCES,
                shot.content_fingerprint,
                required_scene_id=shot.scene_id,
                required_shot_id=shot.id,
            ):
                raise DomainValidationError("current character references must be approved first")
            if not approved(
                ApprovalStage.IDENTITY_WORKFLOW,
                shot.content_fingerprint,
                required_scene_id=shot.scene_id,
                required_shot_id=shot.id,
            ):
                raise DomainValidationError("the current identity workflow must be verified first")
            if not approved(ApprovalStage.ROUGH_CUT, workspace_fingerprint):
                raise DomainValidationError("approve the rough cut before final footage")
        if stage is ApprovalStage.ROUGH_CUT:
            if not workspace.scenes or not workspace.shots:
                raise DomainValidationError("rough cut requires scenes and shots")
            for current_scene in workspace.scenes:
                for required in (ApprovalStage.TELUGU_SCRIPT, ApprovalStage.PRONUNCIATION):
                    if not approved(
                        required,
                        current_scene.content_fingerprint,
                        required_scene_id=current_scene.id,
                    ):
                        raise DomainValidationError(
                            "approve every current script and pronunciation before the rough cut"
                        )
            for current_shot in workspace.shots:
                for required in (ApprovalStage.VOICE_PERFORMANCE, ApprovalStage.STORYBOARD):
                    if not approved(
                        required,
                        current_shot.content_fingerprint,
                        required_scene_id=current_shot.scene_id,
                        required_shot_id=current_shot.id,
                    ):
                        raise DomainValidationError(
                            "approve every current voice performance and storyboard "
                            "before the rough cut"
                        )
        milestone_durations = {
            ApprovalStage.DIALOGUE_90_SECONDS: 90_000,
            ApprovalStage.SEQUENCE_180_SECONDS: 180_000,
            ApprovalStage.FILM_900_SECONDS: 900_000,
        }
        if stage in milestone_durations:
            assert evidence is not None
            if (
                evidence.kind is not AssetKind.VIDEO
                or evidence.state is not AssetState.INSPECTED
                or evidence.metadata is None
                or evidence.metadata.duration_ms < milestone_durations[stage]
            ):
                raise DomainValidationError(
                    "milestone evidence must be an inspected video meeting the target duration"
                )
            prerequisites = {
                ApprovalStage.DIALOGUE_90_SECONDS: (ApprovalStage.ROUGH_CUT,),
                ApprovalStage.SEQUENCE_180_SECONDS: (ApprovalStage.DIALOGUE_90_SECONDS,),
                ApprovalStage.FILM_900_SECONDS: (
                    ApprovalStage.DIALOGUE_90_SECONDS,
                    ApprovalStage.SEQUENCE_180_SECONDS,
                ),
            }[stage]
            if not all(approved(item, workspace_fingerprint) for item in prerequisites):
                raise DomainValidationError("real-media milestones must be approved in sequence")
            if stage is ApprovalStage.FILM_900_SECONDS:
                if not approved(ApprovalStage.ADJACENT_SHOT_CONTINUITY, workspace_fingerprint):
                    raise DomainValidationError("approve adjacent-shot continuity first")
                for current_shot in workspace.shots:
                    for required in (
                        ApprovalStage.VISUAL_PERFORMANCE,
                        ApprovalStage.LIP_SYNC,
                    ):
                        if not approved(
                            required,
                            current_shot.content_fingerprint,
                            required_scene_id=current_shot.scene_id,
                            required_shot_id=current_shot.id,
                        ):
                            raise DomainValidationError(
                                "approve every current visual performance and lip-sync first"
                            )
        if stage is ApprovalStage.FINAL_SOUND_MIX:
            assert evidence is not None
            metadata = evidence.metadata
            if (
                evidence.kind not in {AssetKind.AUDIO, AssetKind.VIDEO}
                or evidence.state is not AssetState.INSPECTED
                or metadata is None
                or metadata.sample_rate is None
                or metadata.channels is None
                or metadata.sample_count is None
                or metadata.duration_ms < project.target_duration_ms
            ):
                raise DomainValidationError(
                    "final sound evidence must be inspected, audio-bearing, and cover the target"
                )
            if not approved(ApprovalStage.FILM_900_SECONDS, workspace_fingerprint):
                raise DomainValidationError("approve the 900-second film milestone first")
        fingerprint = (
            shot.content_fingerprint
            if shot is not None
            else (scene.content_fingerprint if scene is not None else workspace_fingerprint)
        )
        return await self.films.add_approval(
            FilmApproval(
                id=self.identifiers.new_approval_id(),
                project_id=project_id,
                owner_id=self.owner_id,
                stage=stage,
                subject_fingerprint=fingerprint,
                approved_at=self.clock.now(),
                scene_id=scene_id,
                shot_id=shot_id,
                evidence_asset_id=evidence_asset_id,
            )
        )
