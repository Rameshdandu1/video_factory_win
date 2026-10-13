# Telugu Short-Film Contract v1

Status: Accepted; planning, persistence, derived readiness, browser review, and gated rough-cut worker implemented

## Target

The `telugu_short_film_900` project preset is Telugu (`te`), long-form, landscape by default,
and targets exactly 900,000 milliseconds. `titles_and_credits_within_target` explicitly controls
whether title and credit time consumes that target. The preset is an assembled film workflow, not a
request for one continuous diffusion generation.

## Creative records

Scenes and shots are distinct, versioned records. A scene owns Telugu script, pronunciation notes,
target timing, and structured continuity: location, lighting, wardrobe, props, physical state, and
character positions. A shot belongs to one scene and owns one independently replaceable visual
unit, its storyboard image, dialogue workflow, and identity workflow.

Every shot requires permissioned character-reference image assets. Seed or character metadata
reuse is never treated as identity preservation. The shot must additionally choose either:

- `reference_generation`, followed by approval of real video evidence from the pinned,
  reference-driven provider; or
- `approved_source_footage`, with the attached permissioned source video approved as evidence.

Dialogue is explicitly `tts` or `recorded`. Recorded Telugu dialogue references an uploaded audio
asset and is not a secondary or fallback path. TTS does not accept a recorded-audio field. Neither
path claims dependable emotional acting from an unqualified emotion prompt; performance is judged
from media and approved separately.

## Approval order

Current fingerprints bind approvals to the exact scene, shot, or complete edit. An edit makes only
dependent approvals stale; unrelated approved shots remain reusable.

1. Approve every scene's Telugu script and pronunciation.
2. For every shot, approve character references, identity-workflow evidence, voice performance,
   and storyboard.
3. Render and approve a rough film from the approved audio and storyboard images.
4. Generate and approve final shots independently. Visual performance cannot be approved before
   the current rough cut. Lip-sync is a separate approval.
5. Approve adjacent-shot continuity and the final sound mix separately.

The application derives a restart-safe readiness report from the current project, scene, shot, and
approval fingerprints. It lists each ordered adjacent-shot boundary, including cross-scene changes
to location, lighting, wardrobe, props, physical state, and character positions. This report is a
review aid, not an automatic continuity-quality judgment. The project-wide continuity approval is
valid only for the complete current edit fingerprint.

The application records these stage names independently: `telugu_script`, `pronunciation`,
`voice_performance`, `visual_performance`, `lip_sync`, `adjacent_shot_continuity`, and
`final_sound_mix`, plus the required identity, storyboard, and rough-cut gates.

## Real-media acceptance sequence

Acceptance evidence must be an inspected, owner-scoped media asset. The enforced sequence is:

1. `dialogue_90_seconds`: an inspected video lasting at least 90,000 milliseconds;
2. `sequence_180_seconds`: an inspected video lasting at least 180,000 milliseconds; then
3. `film_900_seconds`: an inspected video lasting at least 900,000 milliseconds.

The 900-second milestone additionally requires current shot visual/lip-sync approvals and current
adjacent-shot continuity. Final sound approval follows the film milestone and requires inspected
audio-bearing evidence whose measured duration covers the project target. A file's measured
duration, by itself, never establishes film quality or passes this contract.

## Recovery and replacement

PostgreSQL is authoritative for scene, shot, and approval records. Scene and shot writes use
optimistic versions. Approval subject fingerprints are compared to the current content fingerprints
after a restart, and readiness is recomputed rather than persisted separately. Correcting one line
or replacing one shot therefore invalidates that subject and current-edit approvals without
deleting unrelated approved assets or approvals.

## Honest runtime boundary

This phase implements the preset, records, validation, approval gates, UI/API operations, and an
opt-in FFmpeg worker that assembles approved storyboard images with approved recorded dialogue. The
worker remains disabled until its exact binaries pass the checked-in real-media qualification
harness. Telugu TTS, final-footage generation, lip-sync, emotional acting, final sound mixing, and
all real 90/180/900-second acceptance runs remain unqualified and are not claimed.
