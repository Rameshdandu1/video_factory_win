from __future__ import annotations

import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from video_app.application.projects import (
    CreateProject,
    GetProject,
    ListProjects,
    ProjectNotFoundError,
    ProjectRevisionConflictError,
    UpdateProject,
)
from video_app.domain.projects import (
    AspectRatio,
    BudgetPolicy,
    ExportSettings,
    Project,
    ProjectDraft,
    ProjectMode,
    ProviderSelections,
)

NOW = datetime(2026, 10, 12, tzinfo=timezone.utc)


@dataclass
class FixedClock:
    value: datetime = NOW

    def now(self) -> datetime:
        return self.value


class FixedIdentifiers:
    def new_project_id(self) -> str:
        return "project_fixed"


class MemoryProjects:
    def __init__(self) -> None:
        self.items: dict[str, Project] = {}

    async def create(self, project: Project) -> Project:
        self.items[project.id] = project
        return project

    async def get(self, owner_id: str, project_id: str) -> Project:
        project = self.items.get(project_id)
        if project is None or project.owner_id != owner_id:
            raise ProjectNotFoundError(project_id)
        return project

    async def list(self, owner_id: str, *, limit: int) -> tuple[Project, ...]:
        return tuple(item for item in self.items.values() if item.owner_id == owner_id)[:limit]

    async def update(self, project: Project, *, expected_version: int) -> Project:
        current = self.items.get(project.id)
        if current is None or current.owner_id != project.owner_id:
            raise ProjectNotFoundError(project.id)
        if current.version != expected_version:
            raise ProjectRevisionConflictError("stale")
        self.items[project.id] = project
        return project


def _draft(title: str = "Conversation") -> ProjectDraft:
    return ProjectDraft(
        title=title,
        language="en",
        mode=ProjectMode.SHORT,
        target_duration_ms=30_000,
        aspect_ratio=AspectRatio.LANDSCAPE,
        export_settings=ExportSettings(1280, 720, 30),
        providers=ProviderSelections(video="wan21", speech="uploaded"),
        budget_policy=BudgetPolicy(),
    )


class ProjectUseCaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_project_use_cases_enforce_owner_scope_and_version(self) -> None:
        repository = MemoryProjects()
        clock = FixedClock()
        created = await CreateProject(repository, clock, FixedIdentifiers(), "owner_one")(_draft())

        self.assertEqual(await GetProject(repository, "owner_one")(created.id), created)
        self.assertEqual(await ListProjects(repository, "owner_one")(), (created,))
        with self.assertRaises(ProjectNotFoundError):
            await GetProject(repository, "owner_two")(created.id)

        clock.value += timedelta(seconds=1)
        updated = await UpdateProject(repository, clock, "owner_one")(
            created.id,
            _draft("Revised"),
            expected_version=1,
        )
        self.assertEqual(updated.version, 2)
        self.assertEqual(updated.title, "Revised")

        with self.assertRaises(ProjectRevisionConflictError):
            await UpdateProject(repository, clock, "owner_one")(
                created.id,
                _draft("Stale"),
                expected_version=1,
            )
