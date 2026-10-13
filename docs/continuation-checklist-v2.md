# Production Workflow Continuation Checklist

## Before touching Runpod

- [ ] Record deployed Git commit and confirm whether it has uncommitted source changes.
- [ ] Export a redacted configuration key inventory; never copy secret values into Git or logs.
- [ ] Record Pod/container image, GPU model/UUID, driver, CUDA, Python, PyTorch, free disk/VRAM, and
      running process ownership.
- [ ] Identify which storage is container disk, Pod volume, or network volume; test persistence with
      non-production sentinel data before relying on it.
- [ ] Back up PostgreSQL and media independently and test restoration to a disposable target.
- [ ] Record Alembic revision and run new migrations against a restored populated copy first.
- [ ] Inventory model/checkpoint paths by opaque label, exact upstream revision, size, and digest.
- [ ] Record sample-video job IDs/storage keys without moving or re-encoding the media.

## Phase gates

### Reference-driven film addendum

- [x] Phase 1: audit, ADR-007, explicit library asset scope, reusable entities, immutable version
      bindings, migration `20261013_0007`, owner-scoped v2 APIs, and Film Library controls.
- [x] Phase 2: ADR-008, migration `20261013_0008`, immutable project Film Bible pins,
      ambiguity-aware name/alias resolution, typed shot bindings, affected-shot reporting, and
      explicit selective version adoption controls.
- [x] Phase 3: ADR-009, migration `20261013_0009`, exact source/mask and transform pins,
      deterministic server RGBA rasterization, authoritative preview, and exact-output approval.
- [x] Phase 4 implementation: isolated pinned Wan2.2 TI2V adapter, capability/preflight checks,
      immutable manifests, v2 UI/API, input-plumbing tests, and opt-in GPU harness.
- [ ] Phase 4 deployment gate: execute the harness on the authorized target GPU and configure its
      approved qualification report before enabling the runtime.
- [x] Phase 5: bounded reference-video inspection, trims, previews, purposes, and approved guidance.
- [x] Phase 6 implementation: pinned VACE/Animate adapters, explicit input roles, frozen constraint
      plans, opt-in controls, cancellation, and conflict rejection.
- [ ] Phase 6 deployment gate: execute both qualification harnesses on the authorized target GPU and
      approve their reports before enabling either runtime.
- [x] Phase 7A implementation: ADR-013, migration `20261013_0013`, immutable approved storyboard/
      recorded-dialogue manifests, canonical cancellable queue worker, measured FFmpeg rough-cut
      output, scoped v2 API/UI, and an opt-in real-media qualification harness.
- [ ] Phase 7A deployment gate: run the FFmpeg qualification harness with authorized image/audio
      fixtures and configure its reviewed report before enabling the dedicated rough-cut worker.
- [x] Phase 7B implementation: derived continuity review, inspected final-audio dependency gates,
      restart recovery, and deterministic house/temple acceptance fixtures.
- [ ] Phase 7B real-media gate: capture and review authorized house/temple end-to-end evidence;
      offline fixtures do not establish artistic or media quality.
- [x] Phase 8 implementation: ADR-015, migration `20261013_0014`, explicit audio timeline items,
      immutable approved-timeline manifests, exact worker routing, bounded visual normalization,
      audio mix, pinned-font Telugu ASS titles/captions, measured MP4, scoped v2 API/UI, and an
      operator-review qualification harness.
- [ ] Phase 8 deployment gate: run the final-timeline qualification harness with a full-duration
      authorized audio fixture; visually/audibly review the retained MP4 and approve the exact
      FFmpeg, ffprobe, font, and output-profile report before enabling its dedicated worker.

- [ ] Phase 1: projects/assets/revisions/uploads/API v2/UI and populated-schema migration tests.
- [x] Phase 2 code: pinned FFmpeg/ffprobe/font, bounded media inspection, approved timeline,
      titles/captions, explicit audio mix, immutable queue job, and final export UI.
- [ ] Phase 2 real-media gate: review the retained renderer-qualification MP4 and authorized short
      export fixture; offline command tests do not establish Telugu glyph or audio quality.
- [ ] Phase 3: pinned Indic Parler/Kokoro runtimes, voices, Dialogue Studio, approvals, audio timing.
- [ ] Phase 4: isolated pinned MuseTalk, manual ROI review, alternating-shot two-character project.
- [ ] Phase 5: chapters, dependency invalidation, caching, budgets, restart recovery, 3,600-second
      bounded assembly fixture.
- [ ] Phase 6: opt-in pinned InfiniteTalk, aligned two-track schema, speaker mapping, GPU qualification.
- [ ] Phase 7: optional pinned local script assistant, secure operations, complete PostgreSQL/browser CI.

## Telugu 900-second acceptance gates

- [x] Persist distinct scene and shot revisions with structured continuity and dependency fingerprints.
- [x] Require character references, storyboard, explicit dialogue source, and identity workflow per shot.
- [x] Persist separate approvals and enforce rough-cut-before-final-footage ordering.
- [ ] Qualify and approve a real 90-second Telugu dialogue scene.
- [ ] Qualify and approve a real three-minute sequence after the 90-second gate.
- [ ] Qualify and approve the assembled 15-minute film after both earlier gates.
- [ ] Approve adjacent-shot continuity and final sound independently; do not infer acceptance from
      the MP4 duration.

Every phase must update `docs/implementation-status-v2.md` using the four independent columns: code,
automated tests, runtime configured, and real media/GPU verified.

## Operator-only actions

Model provisioning, Runpod Pod creation/stopping/termination, paid GPU tests, deployment migrations,
and deletion/retention operations require separate explicit authorization. Until then, use offline
tests and checked-in placeholder acceptance definitions only.
