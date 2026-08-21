# ADR-003: PostgreSQL job store and durable queue

Status: Accepted on 2026-08-21

## Context

Video generations are expensive, long-running jobs whose state must survive API and worker restarts. Job submission, cancellation, claims, and terminal transitions must be atomic. Splitting authoritative state across a database and a separate broker would introduce a dual-write failure mode before the MVP needs the throughput or routing features of a dedicated broker.

## Decision

- Use PostgreSQL 18, kept on its current supported minor release, as the authoritative job store and durable MVP work queue.
- Use SQLAlchemy 2 async APIs for persistence mapping, asyncpg as the PostgreSQL driver, and Alembic for forward-only schema migrations.
- Enqueue by inserting a `queued` job in the same transaction that persists its normalized request.
- Workers claim eligible jobs in a short transaction using `FOR UPDATE SKIP LOCKED`, then set `running`, a unique lease token, worker ID, attempt ID, lease expiry, and start time before committing.
- Generation runs outside database transactions and without retaining row locks.
- Workers renew time-bounded leases with conditional updates that require the current lease token.
- Completion, failure, cancellation, progress, and heartbeat writes use conditional atomic updates. A stale worker whose lease token no longer matches cannot publish state or output.
- An expired running lease is terminally failed with a safe worker-loss code. It is not automatically requeued; retries remain explicit new jobs under Generation Contract v1.
- Workers poll PostgreSQL for correctness. `LISTEN/NOTIFY` may be added only as a latency optimization and never as the durable work record.
- Do not add Redis, Celery, RabbitMQ, Kafka, or another queue in the MVP.

## Queue ordering and capacity

Eligible jobs are claimed oldest first by `(created_at, id)`. The queue is bounded by configuration. Queue-capacity admission and insertion must occur under a transaction-level PostgreSQL advisory lock so concurrent submissions cannot exceed the configured bound.

## Recovery

A recovery operation periodically finds `running` jobs whose leases expired. It conditionally changes them to `failed` only when their lease token and expiry still match. It records `GENERATION_FAILED` internally as worker loss, cleans known temporary artifacts, and leaves retry decisions to the user.

## Consequences

- Queue insertion and authoritative state persistence are one transaction.
- Cancellation/completion races and stale-worker writes can be resolved in PostgreSQL.
- Operational complexity is lower than running a separate broker.
- PostgreSQL polling adds small query load, acceptable for bounded GPU throughput.
- Advanced routing, cross-region delivery, or much higher queue throughput may require a dedicated broker through a superseding ADR.
- Integration tests require PostgreSQL; unit tests continue to use in-memory fakes and require no service.

