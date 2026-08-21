# Coding Standards

## Python

- Target Python 3.10 through 3.12 until Wan2.1 compatibility is verified beyond that range.
- Use explicit types for public and internal boundaries. `Any` requires a narrow adapter boundary and an explanatory comment.
- Prefer immutable domain value objects. Use enums for finite states and exhaustive handling for transitions.
- Keep functions focused, deterministic by default, and free of hidden I/O.
- Raise specific exceptions. Catch only errors that can be handled, enriched, translated, or cleaned up.
- Use structured logging with job IDs; never log tokens, raw private prompts, or input media.

## Async and concurrency

- Use async only for concurrent I/O. Never run CPU/GPU-heavy generation on an event loop.
- Bound queues, workers, retries, timeouts, and external requests.
- Cancellation must be explicit and cleanup-safe. Race-prone state changes belong behind a repository operation with compare-and-set semantics.

## Contracts and validation

- Parse untrusted data at the outermost boundary and convert it into domain types.
- Use domain types internally, not dictionaries with implicit keys.
- Validate media type using content inspection as well as extensions when uploads are introduced.
- Timestamps are timezone-aware UTC. IDs are opaque. Seeds are recorded exactly.

## Tests

- Follow Arrange/Act/Assert and name tests after observable behavior.
- Default tests are offline and GPU-free. Fake ports must model failure and cancellation, not only success.
- Integration tests may use local processes or storage but remain deterministic.
- GPU tests use the `gpu` marker and require an explicit opt-in.

## Tooling

Ruff owns linting and formatting, mypy owns static typing, and pytest owns tests. Do not add overlapping formatters or linters without an ADR.

