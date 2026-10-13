# HTTP API v2: Projects and Film Library

Status: Implemented through derived film readiness and opt-in approved-media rough-cut rendering

This additive contract introduces durable, owner-scoped project records. It does not replace or
change the `/api/v1` quick-generation contract.

## Ownership boundary

Every operation is scoped to the typed `VIDEO_APP_OWNER_ID` setting. A project belonging to another
owner is indistinguishable from a missing project. This supports protected single-owner deployments;
it is not a substitute for authentication in a multi-user service.

## Endpoints

- `POST /api/v2/projects` creates a project and returns `201`.
- `GET /api/v2/projects?limit=50` lists projects for the configured owner, newest first. The limit is
  constrained to 1–100.
- `GET /api/v2/projects/{project_id}` returns one owner-scoped project.
- `PUT /api/v2/projects/{project_id}` updates mutable fields. The body includes `expected_version`;
  stale writes return `409 REVISION_CONFLICT`.
- `POST /api/v2/projects/{project_id}/assets?filename=...&kind=...&rights=...` streams one raw media
  body using its allowlisted `Content-Type` and returns `201`. It accepts PNG, JPEG, WAV, or MP4;
  the server enforces its configured byte limit and verifies container magic before publication.
- `GET /api/v2/projects/{project_id}/assets?limit=100` lists immutable asset metadata. Storage keys
  and host paths are never returned.
- `POST /api/v2/projects/{project_id}/assets/{asset_id}/inspect` runs the configured verified
  inspector and creates a new asset metadata version. Missing pins return
  `503 MEDIA_INSPECTION_UNAVAILABLE`; invalid media returns `422 MEDIA_INSPECTION_FAILED`.
- `POST /api/v2/projects/{project_id}/timelines` creates an immutable timeline revision after
  validating project duration, item bounds, referenced asset ownership, and non-overlapping captions.
- `GET /api/v2/projects/{project_id}/timelines?limit=50` lists newest revisions first.
- `POST /api/v2/projects/{project_id}/timelines/{timeline_id}/approve` atomically records approval
  and advances the project's optimistic version using `expected_project_version`.
- `GET /api/v2/projects/{project_id}/timeline-renders/provider` reports the exact pinned renderer
  profile and truthful qualification state.
- `POST /api/v2/projects/{project_id}/timelines/{timeline_id}/renders` queues an immutable manifest
  only for the project's current approved timeline. `GET .../renders/{job_id}` reads status,
  `POST .../renders/{job_id}/cancel` requests cancellation, and `GET .../renders/{job_id}/output`
  serves only a successful MP4.
- `GET /api/v2/projects/{project_id}/film` returns the persisted scenes, shots, and approvals for a
  Telugu 900-second preset project.
- `GET /api/v2/projects/{project_id}/film/readiness` derives structural blockers, current missing
  approvals, ordered adjacent-shot boundaries, actionable gate flags, and the next project gate.
  It persists no second workflow state and makes no automatic artistic-quality claim.
- `POST /api/v2/projects/{project_id}/film/scenes` creates or optimistically revises a scene.
- `POST /api/v2/projects/{project_id}/film/shots` creates or optimistically revises an independent
  shot after checking every referenced asset's ownership and media kind.
- `POST /api/v2/projects/{project_id}/film/approvals` records one fingerprint-bound approval. The
  API enforces subject scope, real-media evidence, rough-cut prerequisites, and the 90/180/900
  acceptance order.
- `POST /api/v2/library/assets?filename=...&kind=...&rights=...` uses the existing bounded upload
  pipeline to create an owner-scoped reusable source. `GET /api/v2/library/assets` lists it without
  exposing storage paths.
- `POST /api/v2/library/assets/{asset_id}/inspect` runs the same configured, verified, bounded
  inspector used for project assets and records a new exact metadata version.
- `POST|GET /api/v2/library/entities` creates or lists reusable characters, locations, props, and
  shot references. Lists accept a kind, Unicode name/alias query, and a bounded limit.
- `GET|PUT /api/v2/library/entities/{entity_id}` reads or optimistically renames display metadata.
- `POST|GET /api/v2/library/entities/{entity_id}/versions` appends or lists immutable versions with
  exact asset-version/hash/role bindings.
- `POST /api/v2/library/entities/{entity_id}/versions/{version_id}/approve` approves the frozen
  content fingerprint without changing its inputs.
- `POST|GET /api/v2/projects/{project_id}/film-bible/snapshots` creates or lists immutable project
  pin sets containing exact approved entity/version IDs, version numbers, fingerprints, and roles.
- `POST /api/v2/projects/{project_id}/film-bible/snapshots/{snapshot_id}/approve` approves one
  frozen Film Bible fingerprint; it does not rewrite earlier snapshots or shots.
- `GET /api/v2/projects/{project_id}/film-bible/snapshots/{snapshot_id}/resolve?mention=...` resolves
  an exact Unicode display name or alias only inside an approved snapshot and returns `resolved`,
  `ambiguous`, or `unresolved` without guessing.
- `POST|GET /api/v2/projects/{project_id}/film/shots/{shot_id}/bindings` appends or lists immutable
  shot-binding revisions tied to an exact shot version and approved Film Bible snapshot.
- `GET /api/v2/projects/{project_id}/film-bible/affected-shots?entity_id=...&version_id=...` reports
  shots whose latest binding revision consumes that exact version; it performs no mutation.
- `POST|GET /api/v2/projects/{project_id}/film/shots/{shot_id}/starting-frames` creates or lists
  immutable composition revisions. Creation pins the current shot version, one exact shot-binding
  revision, source/mask asset versions and hashes, canvas, ordered transforms, fit/crop and notes.
- `POST /api/v2/projects/{project_id}/film/shots/{shot_id}/starting-frames/{id}/render` creates an
  RGBA PNG through the pinned server renderer and atomically publishes its project asset metadata.
- `GET /api/v2/projects/{project_id}/film/shots/{shot_id}/starting-frames/{id}/preview` serves the
  authoritative server-rendered PNG without exposing a storage key or host path.
- `POST /api/v2/projects/{project_id}/film/shots/{shot_id}/starting-frames/{id}/approve` approves
  only the exact rendered output hash. Content changes require a new composition revision.
- `POST|GET /api/v2/projects/{project_id}/film/shots/{shot_id}/reference-guidance` creates or lists
  immutable reference-video ranges pinned to the current shot, exact shot binding, inspected source
  metadata version/hash, explicit purpose, and bounded trim.
- `GET /api/v2/projects/{project_id}/film/shots/{shot_id}/reference-guidance/{id}/preview` serves the
  exact authorized source for browser playback at the persisted range; it exposes no storage path.
- `POST /api/v2/projects/{project_id}/film/shots/{shot_id}/reference-guidance/{id}/approve` approves
  only the exact guidance fingerprint after review. It makes no identity or performance claim.
- `GET /api/v2/image-generation/provider` reports the exact TI2V provider pin and whether a qualified
  runtime is configured; disabled is a truthful normal state.
- `POST /api/v2/projects/{project_id}/film/shots/{shot_id}/starting-frames/{id}/generations` queues
  one image-conditioned shot only from an approved current composition. The body contains a prompt,
  browser-safe string seed, and owner-scoped idempotency key.
- `GET /api/v2/projects/{project_id}/film/shots/{shot_id}/generations/{job_id}` reads the scoped job;
  `POST .../{job_id}/cancel` cancels it, and `GET .../{job_id}/output` serves only a successful MP4.
- `GET /api/v2/controlled-generation/providers` lists VACE/Animate operations and their truthful
  qualification state, preservation semantics, duration limit, and exact runtime pin.
- `POST /api/v2/projects/{project_id}/film/shots/{shot_id}/starting-frames/{composition_id}/reference-guidance/{guidance_id}/generations`
  queues one controlled shot only when both inputs are current and approved, share the same binding,
  and the selected operation can honor every frozen constraint. Conflicts return
  `409 CONSTRAINT_CONFLICT`.
- `GET /api/v2/projects/{project_id}/film/rough-cuts/provider` reports the exact FFmpeg worker pin,
  export profile, and truthful qualification state.
- `POST /api/v2/projects/{project_id}/film/rough-cuts` queues one immutable 900-second manifest only
  after current Telugu-script, pronunciation, storyboard, and recorded-voice approvals pass. The
  body contains an explicit owner-scoped idempotency key.
- `GET /api/v2/projects/{project_id}/film/rough-cuts/{job_id}` reads the scoped canonical job;
  `POST .../{job_id}/cancel` requests cancellation, and `GET .../{job_id}/output` serves only a
  successful MP4. Responses expose provenance fingerprints but never storage keys or host paths.

Unknown or cross-owner IDs return the corresponding stable project, asset, library, Film Bible, or
film-subject `404` code. Validation failures use the established machine-readable error envelope.
Full schemas are exposed by FastAPI at `/docs` and `/openapi.json`.

## Project invariants

- Modes are `short` and `long`.
- Aspect ratios are `9:16`, `16:9`, and `1:1`.
- Language is a normalized BCP-47-style tag with a conservative character allowlist.
- Duration is stored in integer milliseconds and is bounded to one hour.
- Frame rate uses integer numerator and denominator fields.
- Provider selections are stable identifiers, not provider implementation types.
- Expensive automatic retries default to zero and budget limits are explicit nullable values.
- Each successful update increments `version` exactly once.
- `telugu_short_film_900` locks language to `te`, mode to `long`, and duration to 900,000 ms while
  preserving the explicit `titles_and_credits_within_target` choice.

## Compatibility

Quick generation remains under `/api/v1`. Project creation does not enqueue GPU work, download a
model, inspect media, or mutate the deployed Wan runtime. Subsequent project workflow endpoints must
be added behind their accepted specifications and migrations.

Asset ingestion records the original safe basename, allowlisted media type, byte size, SHA-256,
rights declaration, and opaque internal storage key. It does not claim duration, codecs, streams,
dimensions, sample rate, or channel layout until explicit inspection succeeds. Inspection then adds
integer duration, rational frame rate, dimensions, and/or audio sample metadata without exposing a
path. See [Media Runtime v1](media-runtime-v1.md).

Timeline timing uses integer milliseconds at the API boundary. Each revision has a canonical SHA-256
fingerprint over ordered items and caption content. Approval never edits revision content.

Film endpoint schemas and approval semantics are defined by
[Telugu Short-Film Contract v1](telugu-short-film-v1.md). They do not enqueue or run final media
generation in an API handler. Readiness follows ADR-014 and is recomputed from canonical records so
it resumes safely after an API restart.

Reusable entity/version rules are defined by [Reference Library v1](reference-library-v1.md).
Library approval is source selection approval, not visual-continuity or generation acceptance.
Starting-frame semantics are defined by
[Starting-frame Composition Contract v1](starting-frame-composition-v1.md). Manual layering is not
automatic photorealistic synthesis. Approved-still I2V semantics and safe string seeds are defined by
[Reference-driven Image Generation v1](image-generation-v1.md).
Bounded video-source and approval semantics are defined by
[Reference-video Guidance Contract v1](reference-video-guidance-v1.md).
Controlled provider, constraint, evidence, and qualification semantics are defined by
[Controlled-video Runtime Contract v1](controlled-video-runtime-v1.md).
Rough-cut input, output, process, and qualification semantics are defined by
[Media Runtime v1](media-runtime-v1.md) and ADR-013.
Final approved-timeline export semantics are defined by
[Timeline Render Contract v1](timeline-render-v1.md) and ADR-015.
