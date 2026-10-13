from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from video_app.domain.models import DomainValidationError
from video_app.domain.timelines import (
    CaptionSegment,
    TimelineDraft,
    TimelineItem,
    TimelineItemKind,
    TimelineRevision,
)


def _draft() -> TimelineDraft:
    return TimelineDraft(
        duration_ms=15_000,
        items=(TimelineItem(TimelineItemKind.TITLE_CARD, 0, 15_000, 0, text="Hello"),),
        captions=(CaptionSegment(0, 2_000, "Hello"), CaptionSegment(2_000, 4_000, "World")),
    )


def test_fingerprint_is_deterministic_and_revision_validates_it() -> None:
    draft = _draft()
    fingerprint = draft.fingerprint()
    assert fingerprint == _draft().fingerprint()
    TimelineRevision(
        "timeline_one",
        "project_one",
        "owner_one",
        1,
        draft.duration_ms,
        draft.items,
        draft.captions,
        fingerprint,
        datetime(2026, 10, 12, tzinfo=timezone.utc),
    )


def test_rejects_overlapping_captions_and_out_of_bounds_items() -> None:
    with pytest.raises(DomainValidationError):
        replace(
            _draft(),
            captions=(CaptionSegment(0, 2_001, "Hello"), CaptionSegment(2_000, 4_000, "World")),
        ).validate()
    with pytest.raises(DomainValidationError):
        replace(
            _draft(),
            items=(TimelineItem(TimelineItemKind.TITLE_CARD, 1_000, 15_000, 0, text="Late"),),
        ).validate()
