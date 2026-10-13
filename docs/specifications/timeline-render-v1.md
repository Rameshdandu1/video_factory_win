# Timeline Render Contract v1

Status: Accepted and implemented; runtime unqualified

## Admission

Only the project's current approved immutable timeline may be submitted. The project and a qualified
renderer profile must have identical duration, dimensions, and rational frame rate. Submission uses
an owner-scoped idempotency key and freezes the timeline fingerprint and all exact asset versions,
hashes, metadata, and opaque storage keys.

The v1 visual track contains `image`, `video`, or `title_card` items on layer zero. Ordered items must
start at zero, be contiguous, not overlap, and fill the complete duration. `audio` items are explicit,
may overlap, and are limited to 32. Video audio is ignored. Audio/video inputs must have verified
metadata, contain the required stream, and cover their declared item duration. Images are used only
as still visual inputs.

## Rendering

The worker verifies every input checksum, normalizes each visual segment to the configured output,
concatenates bounded intermediates, mixes explicit audio tracks into stereo 48 kHz AAC, and burns
application-authored ASS titles/captions with a pinned Telugu-capable font. The final MP4 is accepted
only after pinned ffprobe confirms width, height, frame count, duration, and both video and audio
streams. Publication uses the existing atomic artifact store.

FFmpeg and ffprobe execute without a shell. Per-run files use application-controlled names and are
removed after success, cancellation, failure, or lease loss. Remote protocols, browser executable
paths, browser fonts, and browser filter graphs are never accepted.

## Qualification boundary

The provider is disabled until an operator-reviewed report matches the exact FFmpeg, ffprobe, and
font hashes plus the configured output profile. Offline tests establish command/input plumbing and
cleanup logic only; they do not establish codec availability, Telugu glyph quality, mix quality, or
real-media acceptance.
