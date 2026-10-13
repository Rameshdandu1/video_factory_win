"""Versioned project workflow domain types for API v2."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum

from video_app.domain.models import DomainValidationError, _require_non_empty, _require_utc_aware

MAX_PROJECT_DURATION_MS = 3_600_000
LANGUAGE_TAG_PATTERN = re.compile(r"[a-zA-Z]{2,8}(?:-[a-zA-Z0-9]{1,8})*")


class ProjectMode(str, Enum):
    SHORT = "short"
    LONG = "long"


class AspectRatio(str, Enum):
    VERTICAL = "9:16"
    LANDSCAPE = "16:9"
    SQUARE = "1:1"


class ProjectState(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class ProjectPreset(str, Enum):
    STANDARD = "standard"
    TELUGU_SHORT_FILM_900 = "telugu_short_film_900"


@dataclass(frozen=True, slots=True)
class ExportSettings:
    width: int
    height: int
    fps_numerator: int
    fps_denominator: int = 1

    def __post_init__(self) -> None:
        if min(self.width, self.height, self.fps_numerator, self.fps_denominator) <= 0:
            raise DomainValidationError("export dimensions and frame rate must be positive")


@dataclass(frozen=True, slots=True)
class ProviderSelections:
    video: str
    speech: str | None = None
    lip_sync: str | None = None
    caption_alignment: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.video, "video provider")
        for field, value in (
            ("speech provider", self.speech),
            ("lip_sync provider", self.lip_sync),
            ("caption_alignment provider", self.caption_alignment),
        ):
            if value is not None:
                _require_non_empty(value, field)


@dataclass(frozen=True, slots=True)
class BudgetPolicy:
    max_compute_seconds: int | None = None
    max_cost_micros: int | None = None
    automatic_expensive_retries: int = 0

    def __post_init__(self) -> None:
        if self.max_compute_seconds is not None and self.max_compute_seconds <= 0:
            raise DomainValidationError("max_compute_seconds must be positive")
        if self.max_cost_micros is not None and self.max_cost_micros <= 0:
            raise DomainValidationError("max_cost_micros must be positive")
        if not 0 <= self.automatic_expensive_retries <= 3:
            raise DomainValidationError("automatic_expensive_retries must be between 0 and 3")


@dataclass(frozen=True, slots=True)
class ProjectDraft:
    title: str
    language: str
    mode: ProjectMode
    target_duration_ms: int
    aspect_ratio: AspectRatio
    export_settings: ExportSettings
    providers: ProviderSelections
    budget_policy: BudgetPolicy
    preset: ProjectPreset = ProjectPreset.STANDARD
    titles_and_credits_within_target: bool = True

    def normalized(self) -> ProjectDraft:
        return replace(self, title=self.title.strip(), language=self.language.strip().lower())

    def validate(self) -> None:
        normalized = self.normalized()
        if not 1 <= len(normalized.title) <= 200:
            raise DomainValidationError("project title must contain between 1 and 200 characters")
        if (
            len(normalized.language) > 35
            or LANGUAGE_TAG_PATTERN.fullmatch(normalized.language) is None
        ):
            raise DomainValidationError("project language must be a valid language tag")
        if not 1_000 <= normalized.target_duration_ms <= MAX_PROJECT_DURATION_MS:
            raise DomainValidationError("target duration must be between 1 and 3600 seconds")
        if normalized.preset is ProjectPreset.TELUGU_SHORT_FILM_900 and (
            normalized.language != "te"
            or normalized.mode is not ProjectMode.LONG
            or normalized.target_duration_ms != 900_000
        ):
            raise DomainValidationError(
                "Telugu short-film preset requires te, long mode, and a 900-second target"
            )


@dataclass(frozen=True, slots=True)
class Project:
    id: str
    owner_id: str
    version: int
    state: ProjectState
    title: str
    language: str
    mode: ProjectMode
    target_duration_ms: int
    aspect_ratio: AspectRatio
    export_settings: ExportSettings
    providers: ProviderSelections
    budget_policy: BudgetPolicy
    approved_timeline_revision_id: str | None
    created_at: datetime
    updated_at: datetime
    preset: ProjectPreset = ProjectPreset.STANDARD
    titles_and_credits_within_target: bool = True

    def __post_init__(self) -> None:
        _require_non_empty(self.id, "project id")
        _require_non_empty(self.owner_id, "owner id")
        if self.version < 1:
            raise DomainValidationError("project version must be positive")
        ProjectDraft(
            title=self.title,
            language=self.language,
            mode=self.mode,
            target_duration_ms=self.target_duration_ms,
            aspect_ratio=self.aspect_ratio,
            export_settings=self.export_settings,
            providers=self.providers,
            budget_policy=self.budget_policy,
            preset=self.preset,
            titles_and_credits_within_target=self.titles_and_credits_within_target,
        ).validate()
        _require_utc_aware(self.created_at, "created_at")
        _require_utc_aware(self.updated_at, "updated_at")
        if self.updated_at < self.created_at:
            raise DomainValidationError("updated_at cannot precede created_at")

    @classmethod
    def create(
        cls,
        *,
        project_id: str,
        owner_id: str,
        draft: ProjectDraft,
        now: datetime,
    ) -> Project:
        normalized = draft.normalized()
        normalized.validate()
        return cls(
            id=project_id,
            owner_id=owner_id,
            version=1,
            state=ProjectState.DRAFT,
            title=normalized.title,
            language=normalized.language,
            mode=normalized.mode,
            target_duration_ms=normalized.target_duration_ms,
            aspect_ratio=normalized.aspect_ratio,
            export_settings=normalized.export_settings,
            providers=normalized.providers,
            budget_policy=normalized.budget_policy,
            approved_timeline_revision_id=None,
            created_at=now,
            updated_at=now,
            preset=normalized.preset,
            titles_and_credits_within_target=normalized.titles_and_credits_within_target,
        )

    def revise(self, draft: ProjectDraft, *, expected_version: int, now: datetime) -> Project:
        if expected_version != self.version:
            raise ProjectVersionError("project version does not match")
        normalized = draft.normalized()
        normalized.validate()
        _require_utc_aware(now, "updated_at")
        if now < self.updated_at:
            raise DomainValidationError("updated_at cannot precede current project state")
        return replace(
            self,
            version=self.version + 1,
            title=normalized.title,
            language=normalized.language,
            mode=normalized.mode,
            target_duration_ms=normalized.target_duration_ms,
            aspect_ratio=normalized.aspect_ratio,
            export_settings=normalized.export_settings,
            providers=normalized.providers,
            budget_policy=normalized.budget_policy,
            preset=normalized.preset,
            titles_and_credits_within_target=normalized.titles_and_credits_within_target,
            updated_at=now,
        )

    def film_contract_fingerprint(self) -> str:
        """Fingerprint project settings that affect an assembled film's acceptance."""

        payload = {
            "preset": self.preset.value,
            "target_duration_ms": self.target_duration_ms,
            "titles_and_credits_within_target": self.titles_and_credits_within_target,
            "aspect_ratio": self.aspect_ratio.value,
            "export_settings": {
                "width": self.export_settings.width,
                "height": self.export_settings.height,
                "fps_numerator": self.export_settings.fps_numerator,
                "fps_denominator": self.export_settings.fps_denominator,
            },
            "providers": {
                "video": self.providers.video,
                "speech": self.providers.speech,
                "lip_sync": self.providers.lip_sync,
                "caption_alignment": self.providers.caption_alignment,
            },
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ProjectVersionError(RuntimeError):
    """Raised when an edit is based on a stale project version."""
