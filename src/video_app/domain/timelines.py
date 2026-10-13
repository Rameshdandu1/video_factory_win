"""Immutable timeline and caption revision contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from itertools import pairwise

from video_app.domain.models import DomainValidationError, _require_non_empty, _require_utc_aware

MAX_TIMELINE_ITEMS = 500
MAX_CAPTION_SEGMENTS = 2_000


class TimelineItemKind(str, Enum):
    VIDEO = "video"
    IMAGE = "image"
    AUDIO = "audio"
    TITLE_CARD = "title_card"


@dataclass(frozen=True, slots=True)
class TimelineItem:
    kind: TimelineItemKind
    start_ms: int
    duration_ms: int
    layer: int
    asset_id: str | None = None
    text: str | None = None

    def __post_init__(self) -> None:
        if self.start_ms < 0 or self.duration_ms <= 0 or not 0 <= self.layer <= 20:
            raise DomainValidationError("timeline timing and layer are invalid")
        if self.kind in {
            TimelineItemKind.VIDEO,
            TimelineItemKind.IMAGE,
            TimelineItemKind.AUDIO,
        }:
            if self.asset_id is None or self.text is not None:
                raise DomainValidationError("media timeline items require only an asset id")
        elif self.asset_id is not None or self.text is None or not self.text.strip():
            raise DomainValidationError("title cards require text and no asset id")
        if self.text is not None and len(self.text) > 500:
            raise DomainValidationError("title card text is too long")


@dataclass(frozen=True, slots=True)
class CaptionSegment:
    start_ms: int
    end_ms: int
    text: str

    def __post_init__(self) -> None:
        if self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise DomainValidationError("caption timing is invalid")
        if not self.text.strip() or len(self.text) > 500:
            raise DomainValidationError("caption text must contain 1 to 500 characters")


@dataclass(frozen=True, slots=True)
class TimelineDraft:
    duration_ms: int
    items: tuple[TimelineItem, ...]
    captions: tuple[CaptionSegment, ...]

    def validate(self) -> None:
        if not 1_000 <= self.duration_ms <= 3_600_000:
            raise DomainValidationError("timeline duration must be between 1 and 3600 seconds")
        if not 1 <= len(self.items) <= MAX_TIMELINE_ITEMS:
            raise DomainValidationError("timeline must contain between 1 and 500 items")
        if len(self.captions) > MAX_CAPTION_SEGMENTS:
            raise DomainValidationError("timeline has too many caption segments")
        if any(item.start_ms + item.duration_ms > self.duration_ms for item in self.items):
            raise DomainValidationError("timeline item exceeds the finished duration")
        ordered = sorted(self.captions, key=lambda item: (item.start_ms, item.end_ms))
        if any(item.end_ms > self.duration_ms for item in ordered):
            raise DomainValidationError("caption exceeds the finished duration")
        if any(left.end_ms > right.start_ms for left, right in pairwise(ordered)):
            raise DomainValidationError("caption segments must not overlap")

    def fingerprint(self) -> str:
        self.validate()
        payload = {
            "duration_ms": self.duration_ms,
            "items": [
                {
                    "asset_id": item.asset_id,
                    "duration_ms": item.duration_ms,
                    "kind": item.kind.value,
                    "layer": item.layer,
                    "start_ms": item.start_ms,
                    "text": item.text.strip() if item.text is not None else None,
                }
                for item in self.items
            ],
            "captions": [
                {"end_ms": item.end_ms, "start_ms": item.start_ms, "text": item.text.strip()}
                for item in self.captions
            ],
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class TimelineRevision:
    id: str
    project_id: str
    owner_id: str
    revision: int
    duration_ms: int
    items: tuple[TimelineItem, ...]
    captions: tuple[CaptionSegment, ...]
    fingerprint: str
    created_at: datetime
    approved_at: datetime | None = None

    def __post_init__(self) -> None:
        for value, field in (
            (self.id, "timeline id"),
            (self.project_id, "project id"),
            (self.owner_id, "owner id"),
        ):
            _require_non_empty(value, field)
        if self.revision < 1:
            raise DomainValidationError("timeline revision must be positive")
        draft = TimelineDraft(self.duration_ms, self.items, self.captions)
        if draft.fingerprint() != self.fingerprint:
            raise DomainValidationError("timeline fingerprint does not match its content")
        _require_utc_aware(self.created_at, "created_at")
        if self.approved_at is not None:
            _require_utc_aware(self.approved_at, "approved_at")
            if self.approved_at < self.created_at:
                raise DomainValidationError("approved_at cannot precede created_at")
