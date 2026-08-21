# ADR-004: Local artifact storage for the MVP

Status: Accepted on 2026-08-21

## Context

Generated MP4 files are large and do not belong in PostgreSQL or source directories. The MVP is local and single-environment, while future deployment may require object storage. Application and domain contracts must not depend on either implementation.

## Decision

- Store MVP output artifacts on a configured local filesystem root outside the repository.
- Access artifacts only through an application-owned storage port implemented in `infrastructure`.
- Generate opaque server-side object names; never derive a path from prompts, user filenames, or unchecked job IDs.
- Resolve and verify all paths remain below the configured root and reject symlinks/reparse points in managed paths.
- Write to a sibling temporary file, flush and close it, validate the media, compute SHA-256 and byte size, then atomically rename it to the final path.
- Persist only an opaque storage key and public-safe metadata in PostgreSQL. Never expose a host path through the API.
- Clean temporary artifacts after success, failure, cancellation, and expired-lease recovery.
- Keep successful local MVP artifacts until manual operator removal. A production retention policy is required before deployment.

## Consequences

- Local development requires no object-storage service.
- The API can stream artifacts through the storage port without learning host paths.
- Local storage is not suitable for horizontally scaled API/worker hosts without a shared filesystem.
- Migrating to S3-compatible object storage requires a new adapter and operational ADR, but no domain or public-contract change.

