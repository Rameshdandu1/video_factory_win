# ADR-001: Application boundaries

Status: Accepted

## Context

Wan2.1 is a large, hardware-dependent generation runtime. Coupling the product directly to its scripts or internal types would make tests GPU-dependent and future backend changes costly.

## Decision

Use a modular monolith for product logic and an independent GPU worker. Own stable contracts in the domain. Access Wan2.1 exclusively through `backends/wan21/`. Keep web/API, job orchestration, persistence, and backend code in distinct modules with the dependency direction in `docs/architecture.md`.

## Consequences

Normal development and unit tests require no model download or GPU. The adapter adds translation code, and end-to-end behavior still requires marked GPU tests. Runtime frameworks, queue technology, and persistence technology remain undecided and require later ADRs.

