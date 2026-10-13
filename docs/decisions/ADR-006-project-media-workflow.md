# ADR-006: Versioned project and media workflow

Status: Accepted on 2026-10-12

## Context

Generation Contract v1 deliberately owns one prompt-to-video job. The production workflow now
requires durable projects, chapters, versioned scenes and characters, approved audio, captions,
timeline composition, selective regeneration, and bounded long-form assembly. Adding these fields
to `/api/v1/jobs` would break its stable meaning and would couple creative approval to worker lease
state.

The deployed Wan generation path, PostgreSQL leased queue, storage port, FastAPI boundary, and
React/Vite client must remain intact.

## Decision

- Preserve `/api/v1` and the canonical generation job lifecycle unchanged.
- Add project workflow resources below `/api/v2`. Project revisions and creative approval are
  separate from executable job states.
- Store project metadata and immutable revision references in PostgreSQL. Store media through the
  existing storage abstraction, never as database blobs or browser-supplied paths.
- Reuse the existing durable job identity, leases, fencing, cancellation, and recovery for every
  executable task. Extend claims with typed workload capabilities rather than adding another queue.
- Introduce backend-neutral typed ports for speech, media inspection/rendering, caption alignment,
  lip-sync, multi-person dialogue, and optional local script assistance. Concrete model runtimes
  remain isolated worker-side processes or images.
- Enqueued work captures immutable input revisions and fingerprints. Later edits make older outputs
  stale; they never mutate an active job's inputs.
- Start with a scene-list timeline and bounded FFmpeg subprocesses. Long projects are rendered from
  reusable chapters and intermediates rather than decoded fully into Python memory.
- Keep the existing quick single-clip screen. Add project screens within the existing React,
  TypeScript, Vite, and plain-CSS system.
- New providers are disabled until their exact code/model revisions, dependencies, licences,
  capabilities, and target GPU runtime have passed an explicit qualification.

## Consequences

The new workflow is additive and v1-compatible, but it requires forward-only schema migrations,
optimistic concurrency, authorization ownership fields, idempotency records, media provenance, and
new worker capability routing. A failed composition must be retryable without regenerating approved
media. Runtime images will be larger in number because incompatible model stacks are intentionally
kept separate.

Authentication and Runpod topology still require deployment-specific confirmation before public
exposure. This ADR does not authorize provisioning, model downloads, paid GPU execution, deletion,
or changes to the currently deployed model revision.
