# ADR-015: Canonical queued timeline rendering

Status: Accepted on 2026-10-13

## Context

Project Workflow v2 already persists immutable approved timelines, uploaded assets, captions, and a
canonical leased job queue. It still lacks a worker-side final export. Rendering inside FastAPI or
adding an independent render-task state machine would break established process and recovery
boundaries. Rendering arbitrary timeline graphs would also make resource use and FFmpeg filter
construction difficult to bound safely.

## Decision

- Extend the canonical generation job with a `timeline_render` mode and an immutable render manifest.
  The manifest pins the approved timeline revision/fingerprint, project export profile, every exact
  asset version/hash/storage key, ordered items, captions, and exact backend revision.
- Add `audio` as an explicit timeline item kind. Video-asset audio is never selected implicitly;
  every audible input is a separately declared audio item.
- Render v1 accepts one contiguous, non-overlapping layer-zero visual track made from images,
  videos, and title cards, plus at most 32 overlapping uploaded audio items and the approved caption
  track. Unsupported layers, gaps, or overlaps fail before queue admission.
- Use one fixed-duration worker profile per qualified process. The selected project must match its
  width, height, rational frame rate, and duration exactly.
- Route work through the existing PostgreSQL queue to a pinned FFmpeg/ffprobe adapter. Commands use
  fixed argument arrays and application-authored files; browser text never becomes a command,
  executable path, remote URL, or filter expression.
- Use a pinned, hashed Telugu-capable font and an application-authored ASS file for title cards and
  captions. Input text is escaped before serialization. The qualification report must prove title,
  Telugu caption, audio mix, measured output, hash rejection, and cancellation cleanup.
- Add owner-scoped, additive `/api/v2` timeline-render operations. Existing `/api/v1`, rough-cut,
  and generation semantics remain unchanged.

## Consequences

The generation-job table gains additive timeline-render routing and manifest fields; timelines gain
no mutable render state. An edit requires a new approved revision and manifest while old jobs remain
auditable. The first renderer deliberately excludes transitions, arbitrary overlays, source in/out
points, unbounded track counts, and implicit video audio. Runtime enablement remains fail-closed
until exact binary/font pins and a reviewed qualification report are configured.
