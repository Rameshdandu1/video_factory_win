# MVP Requirements v1

Status: Accepted on 2026-08-21

## Goal

Deliver one reliable text-to-video workflow that can be developed and tested without a GPU, then executed by Wan2.1 in an isolated GPU worker without changing the application contract.

## User workflow

1. A user submits a text prompt and supported generation settings.
2. The application creates a queued job and returns its ID.
3. A worker claims the job and reports a truthful state.
4. The user can inspect or cancel the job while it is active.
5. A successful job exposes a previewable and downloadable MP4 through the API.
6. A failed job exposes a stable, safe failure code and whether creating a new job may succeed.
7. The user can list recent jobs, newest first.

## In scope

- Text-to-video mode only.
- One configured logical Wan2.1 text-to-video model at a time.
- Prompt, resolution, frame count, and optional seed.
- Submit, inspect, list, cancel, preview, and download.
- `queued`, `running`, `succeeded`, `failed`, and `cancelled` job states.
- An offline fake backend used by development and CI.
- A real Wan2.1 adapter executed only by a separate GPU worker.
- Local single-user development without authentication.
- Model capability discovery for supported resolutions and frame counts.

## Out of scope

- Image-to-video, video editing, text-to-image, and audio generation.
- Authentication, multiple users, organizations, and collaboration.
- Billing, subscriptions, quotas, and public sharing.
- Prompt enhancement or modification by the application.
- Fine-tuning, training, or model uploads.
- Multi-GPU scheduling, distributed deployment, and autoscaling.
- A public output-deletion operation.
- A production retention guarantee.

## Functional requirements

### Generation

- The application accepts only requests conforming to Generation Contract v1.
- It resolves omitted seeds before enqueueing and persists the resolved seed.
- It validates settings against the selected model's capabilities before accepting work.
- It never exposes local checkpoint paths or arbitrary backend arguments through the public contract.
- Retrying means explicitly submitting a new job. The system never silently retries an expensive generation.

### Jobs

- Job creation returns a stable opaque ID and the normalized request.
- Job transitions follow the state machine in Generation Contract v1.
- Cancellation is idempotent and safe under completion/cancellation races.
- Job lists use cursor pagination, return newest first, and may filter by status.
- Progress is absent unless the backend supplies a reliable measurement.

### Outputs

- Successful output is an MP4 served through an application endpoint, not a filesystem path.
- Output metadata includes dimensions, frame count, duration when known, byte size, SHA-256 checksum, and creation time.
- Output filenames are server-generated and writes are atomic.
- Local MVP outputs remain until manually removed by an operator. Temporary files are removed after every terminal outcome.

### Failures

- Public failures contain a stable code, safe message, retryability, and job/correlation ID.
- Public failures never contain stack traces, credentials, prompts, raw backend exceptions, checkpoint paths, or host paths.

## Non-functional requirements

- Normal unit and architecture tests require no GPU, model weights, or network.
- The API process remains usable without CUDA and never loads a model.
- GPU concurrency is bounded and configurable; one worker must not oversubscribe its device.
- All timestamps are timezone-aware UTC.
- Direct dependencies and the integrated Wan2.1 revision are pinned before real-backend integration.
- Formatting, linting, strict typing, architecture checks, and tests pass in CI.

## Acceptance criteria

- The fake backend completes one end-to-end text-to-video job using the same ports as Wan2.1.
- Validation rejects empty prompts, unknown fields, unsupported models, unsupported dimensions, unsupported frame counts, and invalid seeds.
- Tests cover every allowed and forbidden state transition, idempotent cancellation, and a cancellation/completion race.
- Successful results preserve the normalized request, resolved seed, model revision, and output checksum.
- Failures are translated into the stable error catalogue without leaking internal details.
- The UI can implement submit, list, inspect, cancel, preview, and download using only the public operations in Generation Contract v1.

