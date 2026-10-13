"""Typed HTTP representations for Project Workflow v2."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from video_app.domain.projects import (
    AspectRatio,
    BudgetPolicy,
    ExportSettings,
    Project,
    ProjectDraft,
    ProjectMode,
    ProjectPreset,
    ProjectState,
    ProviderSelections,
)


class ExportSettingsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    width: int = Field(gt=0, le=7680, strict=True)
    height: int = Field(gt=0, le=7680, strict=True)
    fps_numerator: int = Field(gt=0, le=240_000, strict=True)
    fps_denominator: int = Field(default=1, gt=0, le=10_000, strict=True)


class ProviderSelectionsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    video: str = Field(min_length=1, max_length=100, strict=True)
    speech: str | None = Field(default=None, min_length=1, max_length=100, strict=True)
    lip_sync: str | None = Field(default=None, min_length=1, max_length=100, strict=True)
    caption_alignment: str | None = Field(default=None, min_length=1, max_length=100, strict=True)


class BudgetPolicyModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_compute_seconds: int | None = Field(default=None, gt=0, strict=True)
    max_cost_micros: int | None = Field(default=None, gt=0, strict=True)
    automatic_expensive_retries: int = Field(default=0, ge=0, le=3, strict=True)


class ProjectDraftModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200, strict=True)
    language: str = Field(min_length=1, max_length=35, strict=True)
    mode: ProjectMode
    target_duration_ms: int = Field(ge=1_000, le=3_600_000, strict=True)
    aspect_ratio: AspectRatio
    export_settings: ExportSettingsModel
    providers: ProviderSelectionsModel
    budget_policy: BudgetPolicyModel = Field(default_factory=BudgetPolicyModel)
    preset: ProjectPreset = ProjectPreset.STANDARD
    titles_and_credits_within_target: bool = True

    @field_validator("title", "language")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value

    def to_domain(self) -> ProjectDraft:
        return ProjectDraft(
            title=self.title,
            language=self.language,
            mode=self.mode,
            target_duration_ms=self.target_duration_ms,
            aspect_ratio=self.aspect_ratio,
            export_settings=ExportSettings(**self.export_settings.model_dump()),
            providers=ProviderSelections(**self.providers.model_dump()),
            budget_policy=BudgetPolicy(**self.budget_policy.model_dump()),
            preset=self.preset,
            titles_and_credits_within_target=self.titles_and_credits_within_target,
        )


class ProjectUpdateModel(ProjectDraftModel):
    expected_version: int = Field(ge=1, strict=True)


class ProjectModel(BaseModel):
    id: str
    version: int
    state: ProjectState
    title: str
    language: str
    mode: ProjectMode
    target_duration_ms: int
    aspect_ratio: AspectRatio
    export_settings: ExportSettingsModel
    providers: ProviderSelectionsModel
    budget_policy: BudgetPolicyModel
    approved_timeline_revision_id: str | None
    created_at: datetime
    updated_at: datetime
    preset: ProjectPreset
    titles_and_credits_within_target: bool

    @classmethod
    def from_domain(cls, project: Project) -> ProjectModel:
        return cls(
            id=project.id,
            version=project.version,
            state=project.state,
            title=project.title,
            language=project.language,
            mode=project.mode,
            target_duration_ms=project.target_duration_ms,
            aspect_ratio=project.aspect_ratio,
            export_settings=ExportSettingsModel(
                width=project.export_settings.width,
                height=project.export_settings.height,
                fps_numerator=project.export_settings.fps_numerator,
                fps_denominator=project.export_settings.fps_denominator,
            ),
            providers=ProviderSelectionsModel(
                video=project.providers.video,
                speech=project.providers.speech,
                lip_sync=project.providers.lip_sync,
                caption_alignment=project.providers.caption_alignment,
            ),
            budget_policy=BudgetPolicyModel(
                max_compute_seconds=project.budget_policy.max_compute_seconds,
                max_cost_micros=project.budget_policy.max_cost_micros,
                automatic_expensive_retries=project.budget_policy.automatic_expensive_retries,
            ),
            approved_timeline_revision_id=project.approved_timeline_revision_id,
            created_at=project.created_at,
            updated_at=project.updated_at,
            preset=project.preset,
            titles_and_credits_within_target=project.titles_and_credits_within_target,
        )


class ProjectListModel(BaseModel):
    items: tuple[ProjectModel, ...]
