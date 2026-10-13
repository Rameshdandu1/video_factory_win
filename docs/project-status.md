# Project Status

## Completed

- [x] Engineering constitution
- [x] Baseline architecture and dependency direction
- [x] Wan2.1 adapter boundary decision
- [x] MVP Requirements v1 accepted
- [x] Generation Contract v1 accepted
- [x] FastAPI transport framework selected through ADR-002
- [x] PostgreSQL job store and durable queue selected through ADR-003
- [x] Local MVP artifact storage selected through ADR-004
- [x] React, TypeScript, and Vite frontend selected through ADR-005
- [x] Frontend UI Specification v1 and root design system accepted
- [x] Separate frontend API client and single-screen MVP workflow implemented and verified
- [x] Job Persistence Specification v1 accepted
- [x] Framework-independent domain types and backend protocol
- [x] Offline fake generation backend
- [x] Application job use cases and leased worker orchestration
- [x] Safe local artifact-storage adapter
- [x] Docker Compose PostgreSQL development service
- [x] PostgreSQL schema migration and durable job repository
- [x] FastAPI-to-worker offline text-to-video vertical slice
- [x] Wan2.1 code and supported model revisions pinned
- [x] External-process Wan2.1 worker adapter implemented and covered by offline tests
- [x] Fail-closed, evidence-producing Wan2.1 GPU qualification harness implemented
- [x] Static-analysis, architecture-test, and CI scaffolding
- [x] Project Workflow v2 projects, secure assets, inspection metadata, timelines, and captions
- [x] Telugu 900-second film planning, continuity, staged approvals, and acceptance contract
- [x] Owner-scoped reusable film library with immutable approved source versions
- [x] Project Film Bible snapshots, Unicode-safe name resolution, and shot-binding revisions
- [x] Approved starting-frame composition and deterministic server rasterization
- [x] Bounded inspected reference-video trims, scoped previews, purposes, and approval revisions
- [x] Opt-in VACE/Wan Animate adapters, frozen constraint plans, and conflict rejection
- [x] Opt-in approved-storyboard plus recorded-dialogue FFmpeg rough-cut queue and UI
- [x] Immutable approved-timeline FFmpeg render queue, explicit audio mix, Telugu captions, and UI

## Next

- [ ] Capture the existing Runpod deployment/runtime evidence without changing it
- [x] Implement the isolated Wan2.2 TI2V adapter and approved-still generation gate
- [ ] Run and approve the Wan2.2 TI2V qualification harness on the target GPU
- [ ] Run and approve the VACE and Wan Animate qualification harnesses on the target GPU
- [ ] Run and approve the FFmpeg rough-cut qualification harness with authorized fixtures
- [ ] Review and approve the final-timeline FFmpeg/font qualification draft with authorized media
- [ ] Implement the remaining Project Workflow v2 speech, lip-sync, and long-form provider phases
- [ ] Pin and clear each self-hosted provider before enabling it
- [ ] Run and retain the marked Wan2.1 GPU qualification report on target Windows/CUDA hardware
- [ ] Verify subprocess and temporary-file cleanup during real GPU cancellation
- [ ] Lock and record the operator-managed Wan2.1 runtime dependency set after qualification

## Explicitly undecided

- Authentication/protected-gateway implementation and exact Runpod topology
- Production model/checkpoint selection
- Production GPU resource profile and sampler tuning

## Production workflow records

- [ADR-006: Versioned project and media workflow](decisions/ADR-006-project-media-workflow.md)
- [ADR-007: Owner-scoped reusable reference library](decisions/ADR-007-owner-scoped-reference-library.md)
- [ADR-008: Project Film Bible and shot bindings](decisions/ADR-008-project-film-bible-and-shot-bindings.md)
- [ADR-009: Starting-frame composer and approval gate](decisions/ADR-009-starting-frame-composer.md)
- [ADR-010: Wan2.2 TI2V approved-still generation](decisions/ADR-010-wan22-ti2v-image-generation.md)
- [ADR-011: Bounded reference-video guidance](decisions/ADR-011-reference-video-guidance.md)
- [ADR-012: Explicit controlled-video providers](decisions/ADR-012-controlled-video-providers.md)
- [ADR-013: Approved-media rough-cut rendering](decisions/ADR-013-rough-cut-rendering.md)
- [ADR-014: Derived film readiness review](decisions/ADR-014-film-readiness-review.md)
- [ADR-015: Canonical queued timeline rendering](decisions/ADR-015-canonical-timeline-rendering.md)
- [Project Workflow v2](specifications/project-workflow-v2.md)
- [Telugu Short-Film Contract v1](specifications/telugu-short-film-v1.md)
- [Starting-frame Composition Contract v1](specifications/starting-frame-composition-v1.md)
- [Reference-video Guidance Contract v1](specifications/reference-video-guidance-v1.md)
- [Controlled-video Runtime Contract v1](specifications/controlled-video-runtime-v1.md)
- [Media Runtime v1](specifications/media-runtime-v1.md)
- [Timeline Render Contract v1](specifications/timeline-render-v1.md)
- [Provider and dependency manifest](provider-manifest.md)
- [Implementation status](implementation-status-v2.md)
- [Continuation checklist](continuation-checklist-v2.md)
