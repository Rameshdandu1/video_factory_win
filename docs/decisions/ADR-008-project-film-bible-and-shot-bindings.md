# ADR-008: Immutable Project Film Bibles and Shot Bindings

Status: Accepted
Date: 2026-10-13

## Context

The reusable owner-scoped library records approved source versions, but a project must not follow a
moving global "latest" version. Shot descriptions also need Unicode name resolution and an explicit
record of which character identity, wardrobe, location view, prop state, or shot reference was
selected. Editing a library entity's display name must not change a generation input, and publishing
a new library version must not silently alter an approved or running shot.

## Decision

Add append-only project Film Bible snapshots. A snapshot pins approved library versions by opaque
entity/version ID, exact version number, content fingerprint, and a typed role. Snapshot approval
changes only its status and approval timestamp. A project can create a later draft by copying the
current pins and replacing selected pins; previous snapshots stay immutable.

Add append-only shot-binding revisions. Each revision records the film shot version, one approved
Film Bible snapshot, and the exact subset of that snapshot's pins used by the shot. Updating one shot
creates a new binding revision only for that shot. Affected-shot queries inspect each shot's latest
binding revision and never mutate it.

Name and alias resolution is Unicode-normalized and exact. It searches only entities pinned by the
selected approved Film Bible snapshot. A unique match resolves to its opaque ID and pinned versions;
multiple matches are reported as ambiguous, and no match remains unresolved. A leading `@` is a UI
convention, not an identity or permission boundary.

Reuse PostgreSQL, the existing library repository, `/api/v2`, and the project UI. No generation job
is created by this phase, and workers continue to execute only frozen generation contracts.

## Consequences

- Existing `/api/v1` and project/film payloads are unchanged.
- Cross-project reuse is explicit: each project owns its own immutable snapshot while both can pin
  the same owner-approved library version.
- Renames affect current display/search metadata but not pinned IDs, fingerprints, or shot binding
  provenance.
- A version update can be adopted selectively by creating a new snapshot and then creating binding
  revisions only for chosen shots. Unselected shots retain their exact prior versions.
- Snapshot and binding history is retained for restart/recovery and future generation manifests.

## Rejected alternatives

- Store one mutable "current version" on the project: this makes approved shots drift.
- Resolve names across the global owner library: this can select content outside the project's Film
  Bible and makes duplicates unsafe.
- Put version IDs directly into free-form prompts: this is not typed provenance.
- Rewrite all shots when a version changes: unrelated approved work must be preserved.
