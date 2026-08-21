# Coding Rules

These rules apply to the entire repository.

## Product boundaries

- This repository is the application layer. Treat Wan2.1 as an external generation backend; do not copy or casually patch upstream source into the app.
- Keep UI, API, orchestration, persistence, and model-runtime code separated. Application code must depend on a small backend interface, not Wan2.1 internals.
- Start with text-to-video. Add image-to-video, editing, or other modes only behind explicit capabilities.

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

