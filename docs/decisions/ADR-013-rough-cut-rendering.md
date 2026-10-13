# ADR-013: Canonical queued rough-cut rendering

Status: Accepted on 2026-10-13

## Context

The Telugu film contract requires an approved rough film made from approved dialogue audio and
storyboard images before final footage is generated. Rendering can take minutes, must be cancellable,
and must resume safely after a process restart. Running FFmpeg in an API handler or creating a second
render-job lifecycle would violate the existing worker and queue boundaries.

## Decision

- Extend the canonical queued job request with an explicit `rough_cut` mode and an immutable rough-cut
  manifest. Do not create another status model or queue.
- The manifest pins the current film-workspace fingerprint, project export settings, every current
  scene and shot revision, and the exact approved storyboard and recorded-dialogue asset versions,
  storage keys, and SHA-256 values.
- Phase 7A accepts recorded Telugu dialogue only. TTS shots fail before admission until a separately
  qualified speech provider has produced an approved audio asset.
- Route rough-cut jobs only to the exact `ffmpeg-rough-cut` backend revision recorded by the manifest.
- Invoke pinned FFmpeg and ffprobe executables with fixed argument arrays and no shell. Render bounded
  per-shot intermediates, then concatenate them without decoding the whole film into application
  memory.
- Publish only the final validated MP4 through the existing artifact store. Remove intermediates on
  success, cancellation, failure, or lease loss.
- Add only additive `/api/v2` film rough-cut operations. `/api/v1` and all existing generation modes
  retain their meanings.

## Consequences

The generation-job table gains an additive JSON manifest and routing columns. A rough cut remains
stale-but-auditable when its source edit changes; it is never silently rebuilt. Correcting one shot
creates a new manifest while unchanged approved asset versions remain reusable. Runtime enablement
requires exact FFmpeg and ffprobe pins plus operator qualification; offline tests do not establish
real-media acceptance.
