# Architecture

Status: Accepted baseline

## Shape

The application is a modular monolith with an independently deployable GPU worker. First-party Python code lives below `src/video_app/`:

```text
api/             transport and request/response mapping
application/     use cases and job orchestration
domain/          stable business types, rules, and ports
infrastructure/  persistence, queue, filesystem, and external adapters
backends/        video-generation backend adapters
bootstrap.py     API/worker composition root and process entry points
```

The future frontend is a separate client of the API. Its framework is intentionally undecided. The HTTP transport uses FastAPI under ADR-002.

## Dependency direction

```text
api ---------> application ---------> domain
                     ^                  ^
                     |                  |
infrastructure ------+------------------+
backends ------------------------------+
```

`domain` imports only the Python standard library. `application` may import `domain`. `api`, `infrastructure`, and `backends` may import `application` and `domain`. The domain never imports an outer layer. Backend adapters never import API or infrastructure modules.

Cross-layer calls use domain-owned ports and contracts. Composition happens only in an application bootstrap module, added when a runtime framework is selected. `video_app/bootstrap.py` is that composition root: it may import all first-party layers solely to construct process-specific dependency graphs and contains no generation, persistence, transport, or storage policy.

## Ownership

### `domain/`

Owns generation requests, normalized settings, job IDs and states, output metadata, backend capabilities, domain errors, and port protocols. It must not perform network, filesystem, database, subprocess, GPU, or framework I/O.

### `application/`

Owns use cases such as submit, cancel, inspect, and retrieve output. It coordinates ports, enforces transitions, and maps infrastructure failures into stable application errors. It must not import Wan2.1, CUDA, web frameworks, database clients, or concrete queue clients.

### `api/`

Owns FastAPI HTTP transport, Pydantic request/response models, authentication hooks, validation mapping, and serialization. Handlers call one application use case and contain no model, persistence, job, or filesystem logic. Transport models map explicitly to domain models and never become domain types.

### `infrastructure/`

Owns the PostgreSQL job repository/queue, local artifact storage, clocks, identifiers, telemetry, and configuration sources under ADR-003 and ADR-004. SQLAlchemy, asyncpg, Alembic, and filesystem details remain inside this layer. Implementations satisfy domain/application ports and do not contain generation policy.

### `backends/`

Owns adapters for generation engines. `backends/wan21/` is the only first-party package allowed to import Wan2.1. It translates stable domain requests into upstream calls and upstream outputs/errors back into stable results.

## Process boundary

The API validates and enqueues. A GPU worker loads Wan2.1, claims bounded work, reports truthful state, writes output atomically, and always releases temporary/GPU resources. The API process must remain usable without CUDA or model weights.

FastAPI `BackgroundTasks`, route handlers, and lifespan hooks must not execute generation. The API composition root constructs application use cases and concrete ports; it is the only location that wires the transport to implementations.

PostgreSQL is the authoritative job store and durable queue. Workers claim with short `FOR UPDATE SKIP LOCKED` transactions, execute outside the transaction, and use renewable lease tokens for all later writes. Polling guarantees correctness; database notifications may only reduce wake-up latency. Generated media is written atomically through the storage port to a configured local root for the MVP, while PostgreSQL stores only opaque storage keys and metadata.

## Stable contracts

Contracts documented in `docs/contracts/generation.md` are stable. Renaming fields, changing meanings, or removing states requires a versioned migration and an accepted ADR.

## Enforcement

`tests/architecture/test_dependencies.py` checks import direction without importing application modules. CI runs architecture tests, unit tests, linting, formatting verification, and strict type checking.
