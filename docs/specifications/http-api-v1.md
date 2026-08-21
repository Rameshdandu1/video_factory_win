# HTTP API Mapping v1

Status: Implemented mapping of Generation Contract v1 on 2026-08-21

This specification records transport details left open by Generation Contract v1. It does not add operations, job states, generation fields, or public error codes.

## Success responses

- `POST /api/v1/jobs` returns `202` and the normalized job resource.
- Job retrieval and idempotent cancellation return `200` and the current job resource.
- Job listing returns `200` with `{ "items": [...], "next_cursor": string | null }`.
- Model discovery returns `200` with `{ "items": [...] }`.
- Health returns `200` with `{ "status": "ok" }` only after PostgreSQL responds.
- Successful output retrieval returns `200`, `Content-Type: video/mp4`, and a server-generated download filename.

## Safe API errors

Transport errors use this shape:

```json
{
  "code": "INVALID_REQUEST",
  "message": "Request validation failed.",
  "retryable": false,
  "correlation_id": "correlation_opaque_id",
  "job_id": null,
  "fields": ["width"]
}
```

`job_id` is present only when the error safely refers to a known opaque job identifier. `fields` contains field names only and never rejected values. Messages are fixed safe text; raw exceptions, prompts, local paths, and credentials are never returned.

| Condition | HTTP status | Code |
| --- | ---: | --- |
| Invalid JSON shape, field, filter, limit, or cursor | 422 | `INVALID_REQUEST` |
| Unknown or disabled logical model | 422 | `UNSUPPORTED_MODEL` |
| Unsupported capability combination | 422 | `UNSUPPORTED_PARAMETERS` |
| Full bounded queue | 429 | `QUEUE_FULL` |
| Missing job or unavailable output resource | 404 | `JOB_NOT_FOUND` |
| Unhealthy PostgreSQL dependency | 503 | `INTERNAL_ERROR` |
| Unexpected safely handled transport failure | 500 | `INTERNAL_ERROR` |

An output URL exists only for a succeeded job. Requesting output before success or after its artifact is unavailable returns the safe missing-resource response; clients inspect the job resource to distinguish current job state.

## Process boundary

The API process constructs a static capability provider and never constructs or invokes a generation backend. The worker process claims and executes jobs independently. FastAPI background tasks, handlers, and lifespan hooks do not generate video.

