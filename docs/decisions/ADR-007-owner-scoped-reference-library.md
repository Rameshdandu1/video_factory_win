# ADR-007: Owner-Scoped Reusable Reference Library

Status: Accepted
Date: 2026-10-13

## Context

Project media currently belongs to exactly one project. A film needs reusable character, location,
prop, and shot-reference sources that can be selected by multiple authorized projects without
copying bytes or treating editable names as identity. The existing asset store, project workflow,
PostgreSQL database, and `/api/v2` contract must remain canonical.

Names, seeds, and metadata reuse do not prove visual identity. Any future generator must consume a
recorded conditioning input and disclose its actual role.

## Decision

Extend the existing `media_assets` abstraction with an explicit `scope`:

- `project` assets retain a non-null project ID and all existing behavior;
- `library` assets have no project ID and are authorized by owner ID.

Add stable `library_entities`, append-only `library_versions`, and ordered
`library_version_assets`. Entity names and aliases are editable Unicode display metadata. Versions
are content-immutable snapshots: each binding records the exact asset ID, asset metadata version,
SHA-256, reference role, and optional view label. Approval changes only the version status and
timestamp. Character identity and wardrobe, location view and lighting, and prop variant and state
are distinct version kinds.

Use opaque identifiers and optimistic concurrency for entity metadata. Cross-owner reads return the
same not-found response as missing records. Reuse the current upload/storage port and `/api/v2`;
there is no second asset store or API generation.

Project film-bible pins, name resolution, composition, and generation manifests are deliberately
subsequent additive phases. Global “latest” versions will not be read implicitly by a worker.

## Consequences

- Existing `/api/v1` jobs and project asset routes remain compatible.
- `media_assets.project_id` becomes nullable only under a database check that requires
  `scope='library'`; existing rows receive `scope='project'`.
- Source bytes and storage keys are still private and immutable. Names never become paths,
  permission keys, or model identifiers.
- Approved library versions provide exact input provenance, not a promise of visual consistency.
- Referenced assets cannot be hard-deleted by a later retention implementation; it must archive
  them or reject deletion.

## Rejected alternatives

- A parallel library upload table/store: duplicates security and provenance logic.
- Copying a source into every project: obscures reuse and creates divergent hashes.
- Treating a display name or seed as a character ID: not identity preservation.
- Adding library fields directly to film shots before immutable version pins exist: creates moving
  references and unsafe worker behavior.
