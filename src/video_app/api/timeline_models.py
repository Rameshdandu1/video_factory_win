"""HTTP models for immutable timeline revisions."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from video_app.domain.timelines import (
    CaptionSegment,
    TimelineDraft,
    TimelineItem,
    TimelineItemKind,
    TimelineRevision,
)


class TimelineItemModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: TimelineItemKind
    start_ms: int = Field(ge=0, le=3_600_000, strict=True)
    duration_ms: int = Field(gt=0, le=3_600_000, strict=True)
    layer: int = Field(ge=0, le=20, strict=True)
    asset_id: str | None = Field(default=None, min_length=1, max_length=100)
    text: str | None = Field(default=None, min_length=1, max_length=500)

    def to_domain(self) -> TimelineItem:
        return TimelineItem(**self.model_dump())


class CaptionSegmentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_ms: int = Field(ge=0, le=3_600_000, strict=True)
    end_ms: int = Field(gt=0, le=3_600_000, strict=True)
    text: str = Field(min_length=1, max_length=500)

    def to_domain(self) -> CaptionSegment:
        return CaptionSegment(**self.model_dump())


class TimelineDraftModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    duration_ms: int = Field(ge=1_000, le=3_600_000, strict=True)
    items: tuple[TimelineItemModel, ...] = Field(min_length=1, max_length=500)
    captions: tuple[CaptionSegmentModel, ...] = Field(default=(), max_length=2_000)

    def to_domain(self) -> TimelineDraft:
        return TimelineDraft(
            self.duration_ms,
            tuple(item.to_domain() for item in self.items),
            tuple(item.to_domain() for item in self.captions),
        )


class TimelineApprovalModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_project_version: int = Field(ge=1, strict=True)


class TimelineRevisionModel(BaseModel):
    id: str
    project_id: str
    revision: int
    duration_ms: int
    items: tuple[TimelineItemModel, ...]
    captions: tuple[CaptionSegmentModel, ...]
    fingerprint: str
    created_at: datetime
    approved_at: datetime | None

    @classmethod
    def from_domain(cls, timeline: TimelineRevision) -> TimelineRevisionModel:
        return cls(
            id=timeline.id,
            project_id=timeline.project_id,
            revision=timeline.revision,
            duration_ms=timeline.duration_ms,
            items=tuple(
                TimelineItemModel(
                    kind=item.kind,
                    start_ms=item.start_ms,
                    duration_ms=item.duration_ms,
                    layer=item.layer,
                    asset_id=item.asset_id,
                    text=item.text,
                )
                for item in timeline.items
            ),
            captions=tuple(
                CaptionSegmentModel(start_ms=item.start_ms, end_ms=item.end_ms, text=item.text)
                for item in timeline.captions
            ),
            fingerprint=timeline.fingerprint,
            created_at=timeline.created_at,
            approved_at=timeline.approved_at,
        )


class TimelineRevisionListModel(BaseModel):
    items: tuple[TimelineRevisionModel, ...]
