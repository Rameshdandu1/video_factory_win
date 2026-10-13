# Reference-video Guidance Contract v1

Status: Implemented

## Scope

This contract records a reviewed reference-video range for one exact film-shot revision. It covers
inspection, immutable source provenance, trim bounds, an owner-scoped preview, explicit purpose, and
approval. It does not perform reference-driven generation, transcode media, or claim identity or
emotional-performance fidelity.

## Source and inspection

The source must be an allowlisted `video` asset in `inspected` state. Its authoritative metadata
comes from the configured hash-pinned ffprobe process and must include positive duration, dimensions,
and frame-rate numerator/denominator. A guidance revision copies the exact asset ID, metadata
version, SHA-256, inspector revision, duration, dimensions, and frame rate.

A project asset must belong to the target project. A library asset requires entity/version IDs and
must be an exact asset binding in an approved library version pinned by the selected shot-binding
revision. The library binding role must equal the selected purpose.

## Revision and purpose

Each revision pins:

- owner, project, shot, current shot version, and shot-binding revision;
- exact source snapshot and optional immutable library provenance;
- purpose: `motion_performance`, `shot_guidance`, or `review_only`;
- `trim_start_ms`, exclusive `trim_end_ms`, and optional guidance notes;
- a deterministic SHA-256 content fingerprint and timestamps.

The trim must be within the measured source and between 250 and 30,000 milliseconds inclusive.
Notes are NFC-normalized and limited to 2,000 safe characters. Edits create a later revision.

## Preview and approval

The preview route revalidates the pinned source metadata version and SHA-256 before serving the
source. The response uses the stored safe media type and supports normal HTTP media behavior from
the application framework. The API representation includes the trim so the UI seeks to the exact
range and pauses at its end.

Only a draft for the current shot version may be approved. Approval preserves the content
fingerprint and adds `approved_at`; it does not alter the source or trim. Downstream generation must
pin an approved guidance ID and fingerprint explicitly when that capability is implemented.

## Additive API

- `POST|GET /api/v2/projects/{project_id}/film/shots/{shot_id}/reference-guidance`
- `GET /api/v2/projects/{project_id}/film/shots/{shot_id}/reference-guidance/{id}/preview`
- `POST /api/v2/projects/{project_id}/film/shots/{shot_id}/reference-guidance/{id}/approve`
- `POST /api/v2/library/assets/{asset_id}/inspect`

All reads are owner-scoped. Lists accept a limit from 1 to 100. Missing and cross-boundary records
produce the same safe not-found response.
