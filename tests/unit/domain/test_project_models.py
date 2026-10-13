from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from video_app.domain.models import DomainValidationError
from video_app.domain.projects import (
    AspectRatio,
    BudgetPolicy,
    ExportSettings,
    Project,
    ProjectDraft,
    ProjectMode,
    ProjectPreset,
    ProjectVersionError,
    ProviderSelections,
)

NOW = datetime(2026, 10, 12, tzinfo=timezone.utc)


def _draft(**overrides: object) -> ProjectDraft:
    values: dict[str, object] = {
        "title": "  Customer and mechanic  ",
        "language": "TE",
        "mode": ProjectMode.SHORT,
        "target_duration_ms": 30_000,
        "aspect_ratio": AspectRatio.VERTICAL,
        "export_settings": ExportSettings(720, 1280, 30),
        "providers": ProviderSelections(video="wan21", speech="uploaded"),
        "budget_policy": BudgetPolicy(max_compute_seconds=1800),
    }
    values.update(overrides)
    return ProjectDraft(**values)  # type: ignore[arg-type]


def test_create_normalizes_project_and_starts_at_version_one() -> None:
    project = Project.create(
        project_id="project_one",
        owner_id="owner_one",
        draft=_draft(),
        now=NOW,
    )

    assert project.title == "Customer and mechanic"
    assert project.language == "te"
    assert project.version == 1
    assert project.approved_timeline_revision_id is None


def test_project_revisions_are_optimistic_and_immutable() -> None:
    original = Project.create(
        project_id="project_one",
        owner_id="owner_one",
        draft=_draft(),
        now=NOW,
    )
    revised = original.revise(
        _draft(title="Updated conversation"),
        expected_version=1,
        now=NOW + timedelta(seconds=1),
    )

    assert original.title == "Customer and mechanic"
    assert revised.title == "Updated conversation"
    assert revised.version == 2
    with pytest.raises(ProjectVersionError):
        original.revise(_draft(), expected_version=2, now=NOW + timedelta(seconds=1))


@pytest.mark.parametrize("duration", [0, 3_600_001])
def test_project_rejects_duration_outside_supported_assembly_range(duration: int) -> None:
    with pytest.raises(DomainValidationError):
        Project.create(
            project_id="project_one",
            owner_id="owner_one",
            draft=_draft(target_duration_ms=duration),
            now=NOW,
        )


def test_project_rejects_invalid_language_tag() -> None:
    with pytest.raises(DomainValidationError):
        Project.create(
            project_id="project_one",
            owner_id="owner_one",
            draft=_draft(language="../telugu"),
            now=NOW,
        )


def test_telugu_film_preset_locks_language_mode_and_900_second_target() -> None:
    project = Project.create(
        project_id="project_film",
        owner_id="owner_one",
        draft=_draft(
            preset=ProjectPreset.TELUGU_SHORT_FILM_900,
            language="te",
            mode=ProjectMode.LONG,
            target_duration_ms=900_000,
            titles_and_credits_within_target=False,
        ),
        now=NOW,
    )

    assert project.preset is ProjectPreset.TELUGU_SHORT_FILM_900
    assert not project.titles_and_credits_within_target
    within_target = project.revise(
        _draft(
            preset=ProjectPreset.TELUGU_SHORT_FILM_900,
            language="te",
            mode=ProjectMode.LONG,
            target_duration_ms=900_000,
            titles_and_credits_within_target=True,
        ),
        expected_version=1,
        now=NOW + timedelta(seconds=1),
    )
    assert within_target.film_contract_fingerprint() != project.film_contract_fingerprint()
    with pytest.raises(DomainValidationError):
        Project.create(
            project_id="project_invalid_film",
            owner_id="owner_one",
            draft=_draft(
                preset=ProjectPreset.TELUGU_SHORT_FILM_900,
                language="te",
                mode=ProjectMode.LONG,
                target_duration_ms=899_000,
            ),
            now=NOW,
        )
