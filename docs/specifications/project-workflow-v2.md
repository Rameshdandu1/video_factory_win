# Project Workflow v2

Status: Accepted; projects, assets, timelines, Telugu film planning, and bounded timeline rendering implemented

The implemented Phase 1A HTTP mapping is specified in [HTTP API v2: Projects](http-api-v2.md).

## Compatibility boundary

`/api/v1/jobs`, Generation Contract v1, and the existing quick creator remain unchanged. New project
resources use `/api/v2`, decimal-string seeds where applicable, opaque asset IDs, safe errors,
keyset pagination, idempotency keys for expensive submissions, and optimistic concurrency versions.

## Canonical records

All records use stable opaque IDs, UTC timestamps, an owner ID, and an integer version starting at
one. Project-owned records cannot cross owner boundaries.

- **Project:** title, language, `short` or `long` mode, target milliseconds up to 3,600,000, aspect
  ratio, export settings, provider selections, budget policy, lifecycle state, and approved timeline
  revision.
- **Chapter:** project, stable order, title, target timing, and approval state.
- **Scene and scene version:** chapter/order, visual description, shot type, speakers, source/reference
  assets, selected outputs, rational timing, immutable inputs, fingerprint, and approval state.
- **Character and character version:** display name, fictional/permissioned declaration, language,
  permissioned references, appearance notes, voice profile version, and continuity warnings.
- **Voice profile, dialogue line, and audio segment:** provider/voice revision, approved display and
  spoken text, language, delivery hint, pauses, measured audio metadata, scene assignment, and
  approval.
- **Media asset:** opaque storage key, SHA-256, measured streams/duration/dimensions/audio metadata,
  source provenance, rights declaration, and lifecycle state. Paths are never public fields.
- **Caption track:** editable segment timing and text, language, format revision, source, and approval.
- **Timeline revision:** immutable ordered items, rational timing, transitions, overlays, audio
  tracks, caption selections, fingerprint, and approval.
- **Render task:** references one immutable timeline revision and one existing executable job/attempt.
- **Provider manifest:** declared capability, exact revisions, readiness, qualification evidence, and
  licence review.
- **Telugu film scene and shot:** distinct fingerprinted records governed by
  [Telugu Short-Film Contract v1](telugu-short-film-v1.md). Shots reference approved character
  images, a storyboard, an explicit recorded/TTS dialogue path, and a verified reference-generation
  or approved-source-footage workflow.

## Invalidation

Fingerprints include every input that can change an output. Changing dialogue invalidates its speech,
speaking shot, dependent timing/captions, and renders. Changing subtitle styling invalidates only
composition. Unrelated approved scenes remain reusable. Cached media is owner-scoped and keyed by
provider/model revision plus normalized inputs.

## Timing and rendering

Finished duration is distinct from provider clip duration. Timeline positions use integer audio
samples and rational video time bases; API convenience durations are integer milliseconds. FFprobe
provides measured metadata. FFmpeg operations have bounded input size, duration, process time, and
output size, disallow remote protocols, avoid shell interpolation, normalize incompatible inputs,
and publish validated MP4 atomically.

Short presets are 15, 30, and 60 seconds; custom durations require validation. Long presets are 5,
10, 30, and 60 minutes, assembled chapter-by-chapter. A 60-minute project never implies a single
60-minute diffusion request or fully decoded in-memory timeline.

## Provider readiness

Declared, configured, ready, running, unavailable, and GPU-verified are distinct states. Indic
Parler-TTS, Kokoro, MuseTalk, InfiniteTalk, WhisperX-compatible alignment, and a local script server
remain disabled until their manifest entry has an exact pin, complete dependency/licence review,
operator provisioning, readiness checks, and the required qualification evidence.

Manual script entry, uploaded permissioned speech, editable captions, deterministic storyboard
splitting, and FFmpeg composition must not depend on an LLM or hosted paid API.

Bounded worker-side export follows [Timeline Render Contract v1](timeline-render-v1.md). Audio is an
explicit timeline item; video audio is not selected implicitly. The initial render profile requires
one contiguous visual track and rejects unsupported composition instead of guessing.

## Safety and cost labels

The product label is **Self-hosted; infrastructure costs apply.** No browser field accepts commands,
repository URLs, checkpoint paths, remote media URLs, fonts, or executable workflows. Real-person
voice cloning and unreviewed research-only lip-sync weights are out of scope.
