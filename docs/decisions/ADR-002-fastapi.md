# ADR-002: FastAPI transport framework

Status: Accepted on 2026-08-21

## Context

Generation Contract v1 requires typed validation, stable JSON schemas, OpenAPI documentation, async infrastructure I/O, testable transport behavior, and safe video delivery. The API must remain a thin outer adapter and must never execute Wan2.1 or other GPU work in its process.

## Decision

- Use FastAPI as the HTTP API framework.
- Use Pydantic v2 models only as transport validation and serialization types.
- Use Uvicorn as the ASGI development/runtime server.
- Publish the API below `/api/v1` and expose OpenAPI in development.
- Test transport behavior through HTTPX against the ASGI application.
- Map Pydantic transport models explicitly to standard-library domain models and back.
- Keep route handlers limited to validation, mapping, one application use-case call, and serialization.
- Dispatch generation through the application queue port. FastAPI `BackgroundTasks`, route handlers, lifespan hooks, and the API process must not run model generation.
- Build the application and dependency graph in one API composition root. Framework dependency injection may expose constructed use cases to routes but must not contain business logic.

## Dependency placement

FastAPI, Pydantic, Uvicorn, and HTTPX may be imported by `video_app.api` and API tests. `video_app.domain` and `video_app.application` must not import them. Infrastructure and backend packages must not depend on FastAPI request, response, or dependency-injection types.

## Alternatives considered

### Litestar

Litestar provides typed ASGI APIs, OpenAPI, dependency injection, and testing. It is viable, but FastAPI's direct Pydantic conventions, documentation, and ecosystem make the accepted contract easier to implement and maintain.

### Django

Django is appropriate when its integrated ORM, admin, authentication, and server-rendered application model are central. Those features are outside this MVP, and adopting them would add framework ownership beyond the transport layer.

### Flask

Flask is small and mature but would require additional decisions and integrations for typed validation, OpenAPI, async behavior, and schema generation already supplied by FastAPI.

## Consequences

- The transport contract can generate OpenAPI and be tested without a live server.
- The domain remains framework-independent and reusable by the worker and tests.
- API and domain models require deliberate mapping code.
- FastAPI's in-process background facilities are explicitly unsuitable for generation jobs.
- Replacing FastAPI requires explicit approval, a superseding ADR, migration impact analysis, and contract regression tests.

