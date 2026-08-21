# Job Persistence Specification v1

Status: Accepted on 2026-08-21

This specification refines Generation Contract v1 and ADR-003. It defines behavior, not SQL migration syntax.

## Authoritative job record

The PostgreSQL job record must represent:

- Opaque job ID and monotonic record version.
- Current contract state.
- All contract timestamps as timezone-aware UTC.
- Normalized generation request, including resolved seed.
- Backend name and exact model revision when resolved.
- Reliable progress or null.
- Successful output metadata and opaque storage key, or null.
- Safe failure code, message, retryability, and correlation ID, or null.
- Cancellation-request timestamp, or null.
- Worker ID, attempt ID, unguessable lease token, heartbeat time, and lease expiry while claimed.

Database constraints must prevent invalid finite states, invalid progress ranges, a successful job without result metadata, and terminal jobs without `completed_at`. Domain validation remains required; database constraints are defense in depth.

## Atomic claim

A worker claim must be a single short transaction:

1. Select the oldest eligible `queued` job ordered by `(created_at, id)` with `FOR UPDATE SKIP LOCKED`.
2. Change it to `running` only if it is still queued and cancellation has not been requested.
3. Set `started_at` if absent, update `updated_at`, increment the record version, and write worker/attempt/lease fields.
4. Commit before any model or filesystem work.

Each claim uses a cryptographically random lease token. Subsequent worker writes include `WHERE status = 'running' AND lease_token = :token`. Updating zero rows means ownership was lost and the worker must stop publishing progress or results.

## Heartbeats and leases

- Lease duration and heartbeat interval are positive configuration values.
- The heartbeat interval must be less than one third of the lease duration.
- Heartbeats use database time, not worker wall-clock time, to extend expiry.
- A transient heartbeat failure does not grant ownership beyond the stored expiry.
- A worker that cannot confirm renewal before expiry must abort generation when safe and must not publish success.

## Cancellation

- Cancelling `queued` atomically sets `cancelled` and `completed_at`.
- Cancelling `running` first records `cancel_requested_at`; the worker observes it during heartbeats/checkpoints and performs cleanup before conditionally setting `cancelled`.
- Repeated cancellation is idempotent.
- Terminal records remain unchanged.
- A worker success update requires no cancellation request and the matching active lease, ensuring only one terminal outcome wins.

## Failure and recovery

- Backend and output failures conditionally transition the owned running job to `failed`.
- Recovery scans expired running leases in bounded batches.
- Recovery conditionally fails only the lease it observed; a renewed lease is not disturbed.
- Recovery never requeues or reruns generation automatically.
- Database unavailability pauses claims. Workers must not create untracked generation work.

## Listing and pagination

List jobs using keyset pagination ordered by `(created_at DESC, id DESC)`. The opaque cursor encodes the last pair and is integrity-protected by the application. Offset pagination is not used. Status filtering is applied before the keyset predicate.

## Notification optimization

If `LISTEN/NOTIFY` is implemented, the notification carries at most an opaque job ID or wake signal. The job row remains authoritative. Workers poll on startup, after reconnect, after each completed claim, and at a bounded interval even when notifications are enabled.

## Required tests

- Two concurrent workers cannot claim the same job.
- Multiple workers claim distinct jobs in stable order.
- A stale lease token cannot heartbeat, cancel, fail, or succeed a job.
- Cancellation and success races produce exactly one terminal state.
- Expired-lease recovery does not affect a renewed lease.
- Queue admission remains within its configured capacity under concurrent submissions.
- A database failure cannot result in untracked generation.
- Keyset pagination has no duplicates or omissions for a stable dataset.

