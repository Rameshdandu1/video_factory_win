# Reference-driven image generation v1

Status: Accepted

## Submission contract

An image-generation request is scoped to an owner, project, film shot, and approved starting-frame
composition. Submission MUST reject a composition when its shot revision, rendered asset version,
or rendered SHA-256 no longer matches the current authoritative records.

The immutable job manifest contains:

- project, shot, and shot-version identifiers;
- composition identifier, revision, fingerprint, and exact source asset identifier/version/hash;
- required backend name and revision;
- model, task, requested area preset, frame count, normalized prompt, and signed 64-bit seed.

The caller supplies an owner-scoped idempotency key. Reusing that key with the same manifest returns
the existing job. Reusing it with different manifest bytes returns `IDEMPOTENCY_CONFLICT` and never
silently changes queued work.

## Runtime contract

The worker resolves only the manifest's opaque storage key, verifies the source hash, decodes an
allowlisted image, and writes a deterministic RGB PNG derivative beneath the worker data root. The
Wan2.2 subprocess MUST receive that derivative through `--image`. Missing input, unsupported media,
hash mismatch, symlink/reparse input, or subprocess failure fails the job. T2V fallback is forbidden.

On success, persisted evidence includes the approved source SHA-256, normalized derivative SHA-256,
and normalized source dimensions. Output dimensions, frames, and media metadata are validated from
the generated MP4; a 900-second duration alone is never film-quality acceptance.

## HTTP contract

- `GET /api/v2/image-generation/provider`
- `POST /api/v2/projects/{project_id}/film/shots/{shot_id}/starting-frames/{composition_id}/generations`
- `GET /api/v2/projects/{project_id}/film/shots/{shot_id}/generations/{job_id}`
- `POST /api/v2/projects/{project_id}/film/shots/{shot_id}/generations/{job_id}/cancel`
- `GET /api/v2/projects/{project_id}/film/shots/{shot_id}/generations/{job_id}/output`

Seeds are JSON strings in v2 responses and requests so browser clients do not lose signed 64-bit
precision. No response exposes filesystem paths or opaque storage keys.
