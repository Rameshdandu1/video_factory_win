"""Timeline revision use cases and persistence port."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from video_app.application.assets import AssetRepository
from video_app.application.ports import Clock
from video_app.application.projects import ProjectRepository
from video_app.domain.assets import AssetKind
from video_app.domain.models import DomainValidationError
from video_app.domain.timelines import TimelineDraft, TimelineItemKind, TimelineRevision


class TimelineNotFoundError(LookupError):
    """Raised when a timeline is absent or outside its project boundary."""


class TimelineIdentifierFactory(Protocol):
    def new_timeline_id(self) -> str: ...


class TimelineRepository(Protocol):
    async def get(self, owner_id: str, project_id: str, timeline_id: str) -> TimelineRevision: ...

    async def create_revision(
        self,
        *,
        timeline_id: str,
        owner_id: str,
        project_id: str,
        draft: TimelineDraft,
        created_at: datetime,
    ) -> TimelineRevision: ...

    async def list(
        self, owner_id: str, project_id: str, *, limit: int
    ) -> tuple[TimelineRevision, ...]: ...

    async def approve(
        self,
        *,
        owner_id: str,
        project_id: str,
        timeline_id: str,
        expected_project_version: int,
        approved_at: datetime,
    ) -> TimelineRevision: ...


@dataclass(frozen=True, slots=True)
class CreateTimelineRevision:
    projects: ProjectRepository
    assets: AssetRepository
    timelines: TimelineRepository
    clock: Clock
    identifiers: TimelineIdentifierFactory
    owner_id: str

    async def __call__(self, project_id: str, draft: TimelineDraft) -> TimelineRevision:
        project = await self.projects.get(self.owner_id, project_id)
        draft.validate()
        if draft.duration_ms != project.target_duration_ms:
            raise DomainValidationError("timeline duration must match the project target duration")
        media_items = [item for item in draft.items if item.asset_id is not None]
        assets = {
            asset_id: await self.assets.get(self.owner_id, project_id, asset_id)
            for asset_id in sorted(
                {item.asset_id for item in media_items if item.asset_id is not None}
            )
        }
        for item in media_items:
            assert item.asset_id is not None
            expected_kind = {
                TimelineItemKind.VIDEO: AssetKind.VIDEO,
                TimelineItemKind.IMAGE: AssetKind.IMAGE,
                TimelineItemKind.AUDIO: AssetKind.AUDIO,
            }[item.kind]
            if assets[item.asset_id].kind is not expected_kind:
                raise DomainValidationError("timeline item kind does not match its media asset")
        return await self.timelines.create_revision(
            timeline_id=self.identifiers.new_timeline_id(),
            owner_id=self.owner_id,
            project_id=project_id,
            draft=draft,
            created_at=self.clock.now(),
        )


@dataclass(frozen=True, slots=True)
class ListTimelineRevisions:
    projects: ProjectRepository
    timelines: TimelineRepository
    owner_id: str

    async def __call__(self, project_id: str, *, limit: int = 50) -> tuple[TimelineRevision, ...]:
        if not 1 <= limit <= 100:
            raise ValueError("timeline list limit must be between 1 and 100")
        await self.projects.get(self.owner_id, project_id)
        return await self.timelines.list(self.owner_id, project_id, limit=limit)


@dataclass(frozen=True, slots=True)
class ApproveTimelineRevision:
    projects: ProjectRepository
    timelines: TimelineRepository
    clock: Clock
    owner_id: str

    async def __call__(
        self, project_id: str, timeline_id: str, *, expected_project_version: int
    ) -> TimelineRevision:
        project = await self.projects.get(self.owner_id, project_id)
        if project.version != expected_project_version:
            from video_app.application.projects import ProjectRevisionConflictError

            raise ProjectRevisionConflictError("project revision is stale")
        return await self.timelines.approve(
            owner_id=self.owner_id,
            project_id=project_id,
            timeline_id=timeline_id,
            expected_project_version=expected_project_version,
            approved_at=self.clock.now(),
        )
