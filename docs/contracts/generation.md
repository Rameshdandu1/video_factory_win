# Generation Contract v1

Status: Accepted on 2026-08-21

This is the stable application contract for the MVP. Field removal, renaming, semantic changes, new job states, or incompatible transition changes require explicit approval, a migration plan, and an accepted ADR. Additive optional fields may be introduced only when old clients remain valid.

## Conventions

- JSON field names use `snake_case`.
- Timestamps are RFC 3339 strings in UTC.
- IDs are opaque strings; clients must not infer meaning from them.
- Unknown request fields are rejected.
- Public model IDs are logical identifiers, never paths.
- API examples show the transport shape but do not select an API framework.

## Generation request

```json
{
  "mode": "text_to_video",
  "prompt": "A cinematic drone shot over a neon city in gentle rain",
  "model": "wan21-t2v",
  "width": 832,
  "height": 480,
  "frame_count": 81,
  "seed": 42
}
```

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `mode` | string | yes | Exactly `text_to_video` in v1. |
| `prompt` | string | yes | Trimmed length 1 through 2,000 Unicode code points. Content is preserved; v1 performs no prompt rewriting. |
| `model` | string | yes | Must match an enabled model returned by model capability discovery. |
| `width` | integer | yes | Positive and part of the selected model's supported resolution pair. |
| `height` | integer | yes | Positive and part of the selected model's supported resolution pair. |
| `frame_count` | integer | yes | Positive and supported by the selected model. |
| `seed` | integer or null | no | Signed 64-bit integer. When absent or null, the server generates and persists one before enqueueing. |

Resolution is validated as a `(width, height)` pair. Supporting each number independently is insufficient. Backend-specific Wan2.1 flags are adapter configuration and are not public request fields.

## Normalized request

Accepted jobs store and return a normalized request with trimmed prompt, explicit mode, logical model ID, selected dimensions, frame count, and a non-null resolved seed. The original prompt must not be logged by default.

## Job resource

```json
{
  "id": "job_opaque_id",
  "status": "queued",
  "created_at": "2026-08-21T10:00:00Z",
  "updated_at": "2026-08-21T10:00:00Z",
  "started_at": null,
  "completed_at": null,
  "request": {
    "mode": "text_to_video",
    "prompt": "A cinematic drone shot over a neon city in gentle rain",
    "model": "wan21-t2v",
    "width": 832,
    "height": 480,
    "frame_count": 81,
    "seed": 42
  },
  "backend": null,
  "model_revision": null,
  "progress": null,
  "result": null,
  "failure": null
}
```

`backend` and `model_revision` become non-null when execution is resolved. `started_at` is set on entering `running`; `completed_at` is set on entering a terminal state. `updated_at` changes on every persisted transition.

## Job states and transitions

States are exactly `queued`, `running`, `succeeded`, `failed`, and `cancelled`.

| From | Allowed destinations |
| --- | --- |
| `queued` | `running`, `failed`, `cancelled` |
| `running` | `succeeded`, `failed`, `cancelled` |
| `succeeded` | none |
| `failed` | none |
| `cancelled` | none |

Terminal states never transition. Transition persistence must be atomic. If completion and cancellation race, exactly one terminal transition wins. After cancellation wins, output must not be published as successful.

Cancellation requests are idempotent. Cancelling a terminal job returns its unchanged current representation. Cancelling an active job returns the latest representation; a running job may remain `running` briefly while cooperative cleanup completes.

Retries are never implicit. A retry creates a new job with a new ID and may reference the previous job internally without changing it.

## Progress

`progress` is either null or a backend-confirmed object:

```json
{
  "completed_units": 12,
  "total_units": 40,
  "stage": "diffusion"
}
```

Both unit values are non-negative integers and `completed_units` cannot exceed `total_units`. `total_units` must be greater than zero. Stage is a safe display label, not a promise of a stable backend phase. The application must not fabricate progress or estimate completion time in v1.

## Successful result

```json
{
  "media_type": "video/mp4",
  "download_url": "/api/v1/jobs/job_opaque_id/output",
  "width": 832,
  "height": 480,
  "frame_count": 81,
  "duration_seconds": 5.0,
  "size_bytes": 12345678,
  "sha256": "64-lowercase-hexadecimal-characters",
  "created_at": "2026-08-21T10:05:00Z"
}
```

`duration_seconds` may be null only when reliable media inspection cannot provide it. Other fields are required on success. Storage paths and internal object keys are never returned. The output endpoint serves or redirects to the opaque artifact without exposing host paths.

## Failure

```json
{
  "code": "GENERATION_FAILED",
  "message": "Video generation failed.",
  "retryable": true,
  "job_id": "job_opaque_id",
  "correlation_id": "correlation_opaque_id"
}
```

Initial public error catalogue:

| Code | Meaning |
| --- | --- |
| `INVALID_REQUEST` | Request shape or field validation failed. |
| `UNSUPPORTED_MODEL` | Logical model is unknown or disabled. |
| `UNSUPPORTED_PARAMETERS` | Settings are not a supported capability combination. |
| `QUEUE_FULL` | Bounded queue cannot accept more work. |
| `MODEL_UNAVAILABLE` | Configured model/revision cannot currently execute. |
| `INSUFFICIENT_RESOURCES` | Disk, CUDA, or memory preflight failed. |
| `GENERATION_FAILED` | Backend execution failed safely. |
| `OUTPUT_WRITE_FAILED` | Atomic output persistence failed. |
| `JOB_NOT_FOUND` | Opaque job ID does not exist. |
| `JOB_NOT_CANCELLABLE` | Reserved for a future operation requiring an active job; idempotent cancel does not use it for terminal jobs. |
| `INTERNAL_ERROR` | Unexpected internal failure with no safe specific code. |

Raw exceptions, credentials, prompts, local paths, checkpoint paths, CUDA dumps, and stack traces are forbidden in public failures. Transport-specific validation details may identify invalid field names but must not echo sensitive values.

## Model capabilities

A model capability record exposes:

```json
{
  "id": "wan21-t2v",
  "display_name": "Wan2.1 Text to Video",
  "modes": ["text_to_video"],
  "resolutions": [{"width": 832, "height": 480}],
  "frame_counts": [81],
  "enabled": true
}
```

The example values are illustrative configuration, not generation defaults. Actual enabled presets are deployment configuration validated by the backend adapter. Changing defaults or prompt processing requires separate approval and evidence as required by `AGENTS.md`.

## Public operations

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/jobs` | Validate and create a generation job. |
| `GET` | `/api/v1/jobs/{job_id}` | Get the current job representation. |
| `GET` | `/api/v1/jobs` | List recent jobs. |
| `POST` | `/api/v1/jobs/{job_id}/cancel` | Idempotently request cancellation. |
| `GET` | `/api/v1/jobs/{job_id}/output` | Retrieve successful output. |
| `GET` | `/api/v1/models` | Discover enabled models and capabilities. |
| `GET` | `/api/v1/health` | Report application health without loading a model. |

Job listing is newest first, uses opaque cursor pagination, defaults to 20 items, allows 1 through 100 items, and may filter by exact job status. Arbitrary sorting and prompt search are out of scope.

## Local MVP retention

Completed artifacts remain until manually removed by an operator. No public deletion operation exists in v1. Temporary files are removed after success, failure, and cancellation. A configurable production retention policy must be accepted before production deployment.

