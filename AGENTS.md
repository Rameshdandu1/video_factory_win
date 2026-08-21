# Coding Rules

These rules apply to the entire repository.

## Source of truth

Use this priority order when instructions conflict:

1. Current explicit user instruction.
2. This file.
3. Accepted architecture decision records in `docs/decisions/`.
4. `docs/architecture.md` and stable contracts.
5. Versioned specifications.
6. Tests.
7. Existing implementation.
8. Assumptions.

Stop and report unresolved conflicts. Never silently choose between competing sources of truth.

## Read before write

Before changing code, read this file, the relevant specification and ADRs, existing implementation, and existing tests. Search for equivalent functionality before creating a file, type, or function. Extend or reuse the canonical implementation instead of creating a parallel one.

## Product boundaries

- This repository is the application layer. Treat Wan2.1 as an external generation backend; do not copy or casually patch upstream source into the app.
- Keep UI, API, orchestration, persistence, and model-runtime code separated. Application code must depend on a small backend interface, not Wan2.1 internals.
- Start with text-to-video. Add image-to-video, editing, or other modes only behind explicit capabilities.
- Follow the module ownership and dependency rules in `docs/architecture.md`. Do not introduce a new top-level source module without explicit approval and an accepted ADR.

## Python and interfaces

- Support Python 3.10 or newer. Add type hints to all public functions and enable strict type checking for first-party code.
- Prefer small, explicit modules. Avoid global mutable state, wildcard imports, hidden I/O, and import-time model loading.
- Use structured request/result types for generation settings. Validate prompts, dimensions, frame counts, seeds, paths, and resource limits at system boundaries.
- Keep configuration in typed settings loaded from environment variables or config files. Never commit credentials, tokens, machine-specific paths, or secrets.
- Pin direct dependencies and record the Wan2.1 revision used. Dependency upgrades must be deliberate and tested.

## Generation jobs

- Run generation as cancellable jobs outside request handlers. Expose queued, running, succeeded, failed, and cancelled states.
- Every job must have a stable ID, timestamps, model/revision, normalized parameters, seed, output metadata, and a useful failure reason.
- Make retries explicit and idempotent. Never silently restart an expensive generation.
- Check model availability, disk space, CUDA support, and expected VRAM before accepting work when practical. Fail early with actionable errors.
- Release GPU memory and temporary files on success, cancellation, and failure. Bound queues and concurrency; do not oversubscribe a GPU.
- Never log full private prompts or input media by default. Redact credentials and sensitive metadata.

## Media and filesystem safety

- Store uploads, checkpoints, caches, temporary frames, and generated videos outside source directories.
- Accept only allowlisted media formats, enforce size limits, sanitize filenames, and generate server-side storage names.
- Resolve and validate all paths before file operations. Prevent traversal and do not follow untrusted symlinks.
- Write outputs atomically. Preserve provenance in sidecar metadata without embedding secrets.
- Do not commit model weights, generated media, uploads, caches, or local databases.

## Testing and quality

- Unit tests must not require a GPU or download model weights. Use a fake backend for normal test runs.
- Put GPU/model tests behind explicit markers and document their hardware requirements.
- Add regression tests for every bug fix. Test validation, cancellation, failure cleanup, deterministic seed plumbing, and path safety.
- Before merging, run formatting, linting, strict type checks, and the unit suite. Keep tests deterministic and avoid network access unless explicitly marked as integration tests.
- Changes to generation defaults or prompt processing require before/after samples and documented rationale.

## API and UI behavior

- APIs return stable machine-readable error codes plus safe human-readable messages.
- Never expose stack traces, local paths, secrets, or raw backend exceptions to users.
- The UI must show generation status, selected model, key settings, progress when reliable, cancellation, and recoverable errors.
- Do not claim precise progress if the backend cannot measure it; show an indeterminate running state instead.

## Git workflow

- Keep commits focused and reviewable. Do not mix generated files or unrelated formatting with functional changes.
- Do not commit directly generated artifacts. Update documentation when configuration, setup, architecture, or operational behavior changes.
- Preserve upstream license notices when distributing or adapting Wan2.1 code, and review licenses for models and dependencies before release.

## Change control

The following require explicit approval and an ADR before implementation: changing dependency direction, replacing the backend abstraction, selecting or replacing an API/UI framework, selecting a queue or database, changing persistence schemas, changing public APIs, or moving ownership between modules.

For changes touching more than three implementation files, first state the affected files, why each changes, architecture/API/data impact, risks, and verification plan. This does not count generated files or straightforward test fixtures.

Do not invent permanent infrastructure choices when requirements are missing. Prefer a replaceable interface or stop and request the decision.

## Forbidden without approval

- Copying Wan2.1 source into first-party packages or importing its internals outside the Wan adapter.
- Loading models in an API process, route handler, module import, or test collection.
- Letting API, UI, or infrastructure types leak into the domain.
- Adding a second job state model, backend interface, configuration system, or persistence abstraction.
- Changing generation defaults, prompt processing, safety policy, storage schema, or public contract without a specification update.
- Disabling checks, weakening types, deleting tests, or adding broad ignores merely to make CI pass.
- Refactoring, renaming, or formatting unrelated code.

## Definition of done

A change is complete only when its requested behavior works, relevant tests cover it, all existing checks pass, architecture boundaries remain intact, no unrelated files changed, and documentation/contracts are updated where necessary.
