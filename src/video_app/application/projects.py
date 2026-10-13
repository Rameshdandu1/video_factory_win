"""Project workflow ports and use cases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from video_app.application.ports import Clock
from video_app.domain.projects import Project, ProjectDraft, ProjectVersionError


class ProjectNotFoundError(LookupError):
    """Raised when a project is absent or belongs to another owner."""


class ProjectRevisionConflictError(RuntimeError):
    """Raised when optimistic concurrency rejects a stale edit."""


class ProjectIdentifierFactory(Protocol):
    def new_project_id(self) -> str: ...


class ProjectRepository(Protocol):
    async def create(self, project: Project) -> Project: ...

    async def get(self, owner_id: str, project_id: str) -> Project: ...

    async def list(self, owner_id: str, *, limit: int) -> tuple[Project, ...]: ...

    async def update(
        self,
        project: Project,
        *,
        expected_version: int,
    ) -> Project: ...


@dataclass(frozen=True, slots=True)
class CreateProject:
    repository: ProjectRepository
    clock: Clock
    identifiers: ProjectIdentifierFactory
    owner_id: str

    async def __call__(self, draft: ProjectDraft) -> Project:
        project = Project.create(
            project_id=self.identifiers.new_project_id(),
            owner_id=self.owner_id,
            draft=draft,
            now=self.clock.now(),
        )
        return await self.repository.create(project)


@dataclass(frozen=True, slots=True)
class GetProject:
    repository: ProjectRepository
    owner_id: str

    async def __call__(self, project_id: str) -> Project:
        return await self.repository.get(self.owner_id, project_id)


@dataclass(frozen=True, slots=True)
class ListProjects:
    repository: ProjectRepository
    owner_id: str

    async def __call__(self, *, limit: int = 50) -> tuple[Project, ...]:
        if not 1 <= limit <= 100:
            raise ValueError("project list limit must be between 1 and 100")
        return await self.repository.list(self.owner_id, limit=limit)


@dataclass(frozen=True, slots=True)
class UpdateProject:
    repository: ProjectRepository
    clock: Clock
    owner_id: str

    async def __call__(
        self,
        project_id: str,
        draft: ProjectDraft,
        *,
        expected_version: int,
    ) -> Project:
        current = await self.repository.get(self.owner_id, project_id)
        try:
            revised = current.revise(
                draft,
                expected_version=expected_version,
                now=self.clock.now(),
            )
        except ProjectVersionError as error:
            raise ProjectRevisionConflictError("project revision is stale") from error
        return await self.repository.update(revised, expected_version=expected_version)
