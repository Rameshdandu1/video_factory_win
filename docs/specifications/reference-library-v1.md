# Reference Library v1

Status: Phases 1 through 5 implemented (library, Film Bible, shot bindings, starting frames, and
reference-video guidance)

## Scope

This contract defines reusable owner-scoped source records, immutable project Film Bible snapshots,
immutable shot-binding revisions, their approved starting-frame handoff, and bounded approved
reference-video guidance. It does not execute reference-driven generation or establish cinematic
quality.

## Entity and version model

Entity kinds are `character`, `location`, `prop`, and `shot_reference`. An entity has an opaque ID,
editable NFC-normalized display name, zero or more normalized aliases, and an optimistic
`metadata_version`. Renaming preserves the ID and every existing version.

Version kinds are:

- character: `identity`, `wardrobe`;
- location: `location_view`, `lighting_variant`;
- prop: `prop_variant`, `prop_state`;
- shot reference: `shot_reference`.

Each version is append-only and records label, appearance/architecture notes, invariants, story or
variant state, optional voice-profile ID, rights/consent notes, and one or more exact asset bindings.
Bindings include asset ID, asset metadata version, source SHA-256, optional view label, and one role:
`identity_appearance`, `location_or_prop`, `source_layer`, `starting_frame`,
`motion_performance`, `shot_guidance`, or `review_only`.

Identity and starting-frame roles require images. Motion/performance and shot-guidance roles require
videos. Location/prop and source-layer roles require visual media. Missing views remain missing; the
system does not invent or relabel them as supplied evidence.

Approval pins the existing content fingerprint and is not an edit. An approved version means the
owner approved the recorded sources and metadata for selection. It does not mean a future model will
preserve appearance or that a generated clip passed continuity review.

## Asset scope

The canonical upload pipeline validates byte limits, filename safety, allowlisted media signatures,
SHA-256, atomic publication, and rights declaration. `project` assets retain a project ID. `library`
assets are owner-scoped and have a null project ID. A version may bind only owner-matching library
assets.

## API

- `POST|GET /api/v2/library/assets`
- `POST|GET /api/v2/library/entities`
- `GET|PUT /api/v2/library/entities/{entity_id}`
- `POST|GET /api/v2/library/entities/{entity_id}/versions`
- `POST /api/v2/library/entities/{entity_id}/versions/{version_id}/approve`

List endpoints are bounded to 100 records in v1. Entity list accepts `kind` and Unicode-safe
`query` matching against names and aliases. Owner ID comes from deployment settings; multi-user
exposure still requires an authenticated gateway/identity integration.

## Compatibility and next contract

No `/api/v1` field or behavior changes. Existing project media remains project-scoped. Phase 2 will
not read a moving global latest version.

## Project Film Bible and shot bindings

A Film Bible snapshot is append-only and project/owner scoped. Each pin records a typed role plus
the exact approved library entity ID, version ID, version number, version kind, and version
fingerprint. Roles distinguish character identity and wardrobe, location view and lighting, prop
variant and state, and shot reference. Approval pins the snapshot fingerprint; later library
versions create later snapshots and never rewrite an existing one.

Name resolution strips one leading `@`, applies Unicode NFKC case-folding, and performs exact
display-name/alias matching only among entities pinned by the chosen approved snapshot. The result
is `resolved`, `ambiguous`, or `unresolved`. An ambiguous or unresolved mention is never guessed.
Renaming retains the opaque entity ID and therefore preserves existing pins and binding history.

A shot-binding revision records the exact film shot version, approved Film Bible snapshot, and
selected pins. Only pins present in that snapshot are valid. Each update appends a revision. The
affected-shot query reports shots whose latest binding revision consumes an exact entity/version;
adoption consists of creating a later snapshot and new revisions only for explicitly selected
shots.

Additive API operations are:

- `POST|GET /api/v2/projects/{project_id}/film-bible/snapshots`
- `POST /api/v2/projects/{project_id}/film-bible/snapshots/{snapshot_id}/approve`
- `GET /api/v2/projects/{project_id}/film-bible/snapshots/{snapshot_id}/resolve`
- `POST|GET /api/v2/projects/{project_id}/film/shots/{shot_id}/bindings`
- `GET /api/v2/projects/{project_id}/film-bible/affected-shots`

Starting frames are governed by
[Starting-frame Composition Contract v1](starting-frame-composition-v1.md). Production I2V remains
the next phase and may consume only an approved starting-frame revision.

Reference-video trims and approvals are governed by
[Reference-video Guidance Contract v1](reference-video-guidance-v1.md). Approval records an exact
reviewed source and purpose; it is not an identity or performance-quality guarantee.
