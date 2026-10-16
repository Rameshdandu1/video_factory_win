# Production Workflow Implementation Status

Snapshot date: 2026-10-13

## Baseline evidence

- Repository: `Rameshdandu1/video_factory_win`
- Commit: `a1962d4b14b711f6e4abc86df663b0ab75c6441d`
- Current branch/commit: `main` at `a1962d4b14b711f6e4abc86df663b0ab75c6441d`, tracking
  `origin/main`
- The 2026-10-13 reference-library audit began with the prior project/media/Telugu workflow still
  uncommitted in the working tree. Those changes were preserved; no reset or cleanup was performed.
- Local configuration: secret-bearing `.env` present; safely inspected provider value is `fake` with
  logical model `wan21-t2v`, `832x480`, 81 frames
- Python: repository virtual environment uses Python 3.12.14
- Local media/GPU tools: `ffmpeg`, `ffprobe`, and `nvidia-smi` were not found on PATH
- Local PostgreSQL: not exercised in this sandbox; repository migration head is `20261013_0014`
- Runpod: platform confirmed by the owner, but no Pod shell, environment, mount, database, checkpoint,
  generated-media, GPU, CUDA, or deployed-commit evidence was accessible from this checkout

## Automated baseline

| Check | Result |
| --- | --- |
| Ruff lint | Passed |
| Strict mypy | Passed, 39 source files |
| Python tests excluding GPU | 73 passed, 8 PostgreSQL tests skipped, 1 GPU test deselected |
| Frontend Prettier | Passed |
| Frontend ESLint | Passed |
| Frontend strict TypeScript | Passed |
| Frontend Vitest | 66 passed |
| Frontend production build | Passed |

## 2026-10-13 Phase 1 verification

| Check | Result |
| --- | --- |
| Ruff format and lint | Passed, 80 Python/migration/test files |
| Strict mypy | Passed, 72 source files |
| Python tests excluding marked GPU qualification | 106 passed, 12 PostgreSQL tests skipped, 1 GPU test deselected |
| Alembic graph | One head: `20261013_0007` |
| Frontend Prettier / ESLint / strict TypeScript | Passed |
| Frontend Vitest | 74 passed |
| Frontend production build | Passed |

The 12 PostgreSQL tests were not executed because neither `DATABASE_URL` nor
`MIGRATION_TEST_DATABASE_URL` was provided. Docker Desktop was unavailable, so no disposable test
database could be created safely. These skips are not counted as integration success. The checked-in
CI PostgreSQL job is still required to run them without skips. No GPU or real-media test was run.

The PostgreSQL skips are an existing environment gap: `DATABASE_URL` was not exported to the test
process. They are not counted as integration success. A pytest cache write warning occurred because
the sandbox denied `.pytest_cache`; tests still completed.

## 2026-10-13 Phase 4 verification

| Check | Result |
| --- | --- |
| Ruff format and lint | Passed |
| Strict mypy | Passed, 50 first-party source files |
| Python tests excluding GPU | 130 passed, 12 PostgreSQL tests skipped, 2 GPU tests deselected |
| Alembic graph | One head: `20261013_0010` |
| Frontend Prettier / ESLint / strict TypeScript | Passed |
| Frontend Vitest | 78 passed |
| Frontend production build | Passed |

The PostgreSQL skips are not counted as integration success. The Wan2.1 and Wan2.2 real-GPU
qualification suites were not run; the latter remains the explicit runtime-enablement gate.

## 2026-10-13 Phase 5 verification

| Check | Result |
| --- | --- |
| Ruff format and lint | Passed |
| Strict mypy | Passed, 50 first-party source files |
| Python tests excluding GPU | 135 passed, 12 PostgreSQL tests skipped, 2 GPU tests deselected |
| Alembic graph | One head: `20261013_0011` |
| Frontend Prettier / ESLint / strict TypeScript | Passed |
| Frontend Vitest | 79 passed |
| Frontend production build | Passed |

The PostgreSQL skips are not counted as integration success. Verified ffprobe was not configured and
no reference-driven GPU provider consumed a guidance revision, so runtime inspection and real-media
behavior remain unverified.

## 2026-10-13 Phase 6 verification

| Check | Result |
| --- | --- |
| Ruff format and lint | Passed |
| Strict mypy | Passed, 56 first-party source files |
| Python tests excluding GPU | 146 passed, 12 PostgreSQL tests skipped, 3 GPU tests deselected |
| Alembic graph | One head: `20261013_0012` |
| Frontend Prettier / ESLint / strict TypeScript | Passed |
| Frontend Vitest | 80 passed |
| Frontend production build | Passed |

The PostgreSQL skips are not counted as integration success. The added VACE/Animate qualification
harness was collected but not executed; no model weights were downloaded and neither runtime was
enabled. The checks prove immutable manifests, constraint rejection, input-role command plumbing,
runtime report gates, cancellation cleanup logic, and the opt-in UI only—not real-media quality.

## 2026-10-13 Phase 7A verification

| Check | Result |
| --- | --- |
| Ruff format and lint | Passed |
| Strict mypy | Passed, 103 Python source and test files |
| Python tests excluding GPU | 155 passed, 14 environment/qualification tests skipped, 3 GPU tests deselected |
| Alembic graph | One head: `20261013_0013` |
| Frontend Prettier / ESLint / strict TypeScript | Passed |
| Frontend Vitest | 82 passed |
| Frontend production build | Passed |

The skipped FFmpeg qualification harness is not counted as real-media success. PostgreSQL URLs and
approved FFmpeg/ffprobe binaries and fixture media were not configured in this run. Offline checks
prove immutable approved-media manifests, exact runtime/report pins, fixed no-shell commands,
idempotent queue routing, scoped API/UI behavior, and cleanup paths—not real rendering quality.

## 2026-10-13 Phase 7B implementation verification

| Check | Result |
| --- | --- |
| Ruff format and lint | Passed |
| Strict mypy | Passed, 105 Python source and test files |
| Python tests excluding GPU | 158 passed, 14 environment/qualification tests skipped, 3 GPU tests deselected |
| Alembic graph | One head: `20261013_0013`; Phase 7B adds no schema |
| Frontend Prettier / ESLint / strict TypeScript | Passed |
| Frontend Vitest | 85 passed |
| Frontend production build | Passed |

PostgreSQL restart coverage was extended but skipped locally because `DATABASE_URL` was not
configured. The offline house-to-temple fixture proves deterministic boundary derivation and that a
changed shot preserves unrelated current approvals. It is not real media and does not establish
identity, continuity, performance, lip-sync, sound, or film quality. Final-sound admission now
requires inspected audio-bearing evidence covering the project target, but no real final mix was
reviewed in this checkout.

## 2026-10-13 Phase 8 implementation verification

| Check | Result |
| --- | --- |
| Ruff format and lint | Passed |
| Strict mypy | Passed, 112 Python source and test files |
| Python tests excluding GPU | 167 passed, 16 environment/qualification tests skipped, 3 GPU tests deselected |
| Alembic graph | One head: `20261013_0014` |
| Frontend Prettier / ESLint / strict TypeScript | Passed |
| Frontend Vitest | 87 passed |
| Frontend production build | Passed |

PostgreSQL and populated-migration execution were skipped because their database URLs were not
configured. The real FFmpeg timeline qualification harness was collected but not run because exact
FFmpeg/ffprobe/font pins and authorized full-duration audio were not configured. Offline evidence
proves immutable approved-timeline admission, asset-hash pinning, exact worker routing, bounded
command construction, cleanup paths, API/UI behavior, and fail-closed qualification—not Telugu
glyph quality, audio-mix quality, or 90/180/900-second film acceptance.

## Feature truth table

| Capability | Code | Automated tests | Runtime configured | Real media/GPU verified |
| --- | --- | --- | --- | --- |
| Quick single-clip React/FastAPI/PostgreSQL workflow | Implemented | Passed offline; PostgreSQL skipped in this run | Local `.env` uses fake backend | No evidence in this checkout |
| Pinned Wan2.1 external adapter | Implemented | Offline adapter tests passed | Not configured in inspected `.env` | Qualification not executed here |
| Owner-scoped project records and `/api/v2/projects` | Implemented in Phase 1A | Unit/API tests passed; PostgreSQL CI added | Requires migration `20261012_0002` | Not applicable |
| Secure project asset ingestion | Implemented in Phase 1B | Domain/storage tests passed; PostgreSQL CI added | Requires migration `20261012_0003` | Container magic only; ffprobe pending |
| Immutable timelines and editable captions | Implemented in Phase 2B | Domain/client tests passed; PostgreSQL CI added | Requires migration `20261012_0005` | No render executed |
| Telugu 900-second scene/shot planning and approvals | Implemented in Phase 2C | Domain/frontend tests passed; PostgreSQL migration test extended | Requires migration `20261012_0006` | No 90/180/900-second media accepted |
| Owner-scoped reusable film library and immutable source-role versions | Implemented in reference addendum Phase 1 | Unit/frontend tests passed; PostgreSQL tests added but not run locally | Requires migration `20261013_0007` | No model consumed these references |
| Project Film Bible snapshots, name resolution, and shot bindings | Implemented in reference addendum Phase 2 | Domain/application/frontend tests passed; PostgreSQL recovery and migration tests added but not run locally | Requires migration `20261013_0008` | No model consumed these references |
| Starting-frame composition, server rasterization, preview, and exact-output approval | Implemented in reference addendum Phase 3 | Deterministic pixel/hash, alpha/mask, domain, API-contract, frontend, migration, lint and strict-type checks passed; PostgreSQL tests skipped locally | Requires migration `20261013_0009` and pinned Pillow 11.3.0 | No I2V model consumed the approved still |
| Approved-still Wan2.2 TI2V generation | Implemented in reference addendum Phase 4; disabled by default | Offline adapter input-plumbing, manifest/idempotency, routing, API/UI and cancellation-cleanup harness checks passed; PostgreSQL and GPU execution pending | Requires migration `20261013_0010`, exact code/model pins, and an approved qualification report | Not GPU-qualified in this checkout |
| Bounded reference-video guidance | Implemented in reference addendum Phase 5 | Domain/application/API/UI and migration coverage passed offline; PostgreSQL execution pending | Requires migration `20261013_0011` and configured verified ffprobe for new inspections | No reference-driven model consumed the approved guidance |
| VACE/Wan Animate controlled shot generation | Implemented in reference addendum Phase 6; disabled by default | Constraint, input-role, cancellation, config, API-model and UI tests passed offline; PostgreSQL/GPU execution pending | Requires migration `20261013_0012`, exact code/model/checkpoint/FFmpeg pins, and provider-specific approved qualification report | Not GPU-qualified in this checkout |
| Chapters | Not implemented | Not implemented | No | No |
| Pinned bounded ffprobe inspection | Implemented in Phase 2A | Parser/use-case tests passed | Disabled; ffprobe absent locally | No |
| Approved-storyboard plus recorded-dialogue rough cut | Implemented in Phase 7A | Domain/application/backend/runtime/API/UI tests passed; PostgreSQL and real qualification skipped locally | Requires migration `20261013_0013`, exact FFmpeg/ffprobe pins, and approved report | No real rough cut rendered in this checkout |
| Derived film readiness, continuity review, and final-sound gate | Implemented in Phase 7B | Domain/application/API/client/UI tests passed offline; PostgreSQL restart test added but skipped locally | No new schema; final evidence still requires configured inspection/runtime workflow | House/temple fixture is synthetic; no real acceptance evidence reviewed |
| Approved final timeline export | Implemented in Phase 8; disabled by default | Domain/application/backend/runtime/API/client/UI tests passed; PostgreSQL and real qualification skipped locally | Requires migration `20261013_0014`, exact FFmpeg/ffprobe/font pins, fixed output profile, and an operator-approved report | No final timeline rendered or reviewed in this checkout; duration alone is never acceptance |
| Uploaded voice, captions, and music tracks | Implemented as inspected project audio assets, explicit timeline items, and immutable captions; no Dialogue Studio | Admission, manifest, mix-command, API/client/UI tests passed | Inspection and final render require qualified ffprobe/FFmpeg/font runtimes | No real final mix reviewed |
| Indic Parler-TTS / Kokoro | Not implemented at snapshot | Not implemented | No | No |
| MuseTalk | Not implemented at snapshot | Not implemented | No | No |
| InfiniteTalk | Not implemented at snapshot | Not implemented | No | No |
| Long-form assembly and budgets | Bounded approved-timeline assembly implemented; chapters and execution budgets remain pending | Offline final-render tests passed | Final renderer disabled pending qualification | No long-form export reviewed |

## Deployment preservation boundary

No Runpod command, model download, paid GPU run, volume mutation, database migration, or remote write
was performed. The owner must capture the deployed commit, redacted configuration, mount types,
database migration revision, model/checkpoint manifests, container/Python/CUDA versions, and sample
asset IDs before any deployment change. Runpod volume paths must be verified rather than assumed;
network volumes are preferable when data must survive Pod replacement.

## Phase 1A evidence

- Added owner-scoped project creation, retrieval, listing, and optimistic revision updates.
- Added the forward-only `20261012_0002` migration without modifying the generation job schema.
- Added a Projects workspace to the React application while keeping Quick clip and `/api/v1`
  available and unchanged.
- Added a dedicated CI job that applies migrations to PostgreSQL, exercises integration tests, and
  fails if an integration test is skipped.
- Ownership currently comes from the typed `VIDEO_APP_OWNER_ID` deployment setting. This is a
  single-owner deployment boundary, not user authentication; a protected gateway or identity
  integration is still required before multi-user exposure.
- No asset ingestion, timeline/media orchestration, TTS, lip-sync, caption alignment, or final
  rendering is claimed by Phase 1A.

## Phase 1B evidence

- Added raw-stream PNG, JPEG, WAV, and MP4 ingestion with a configurable 50 MiB default limit.
- Added filename/path rejection, extension/content-type allowlisting, magic-byte inspection,
  SHA-256 hashing, opaque server storage names, atomic publication, and cleanup after failure.
- Added immutable owner/project-scoped metadata and forward-only migration `20261012_0003`.
- Added project asset selection/upload/list UI with an explicit rights declaration.
- FFprobe-derived metadata is intentionally not claimed or persisted yet; that remains Phase 2.

## Phase 2A evidence

- Added an exact-version and executable-SHA-pinned ffprobe adapter with no-shell execution, local-file
  protocol restriction, timeout, and output bounds.
- Added versioned measured duration, rational frame rate, dimensions, sample rate, channels, and
  sample-count metadata plus migration `20261012_0004`.
- Added explicit asset inspection API and UI controls with safe unavailable/failure errors.
- The workstation has no ffprobe binary, so runtime configuration and real-media validation remain
  unverified. FFmpeg normalization, audio mixing, captions, and final rendering are not implemented
  or claimed by Phase 2A.

## Phase 2B evidence

- Added immutable, fingerprinted timeline revisions with bounded items and integer-millisecond timing.
- Added editable caption segments with ordered, non-overlapping timing and durable revision history.
- Added owner/project asset-reference validation and atomic timeline approval through project
  optimistic concurrency.
- Added v2 create/list/approve endpoints, a JSON timeline/caption editor, and migration
  `20261012_0005`.
- Timeline persistence is implemented; FFmpeg rendering and real short export remain unverified and
  are not executed in API handlers.

## Phase 2C evidence

- Added the locked `telugu_short_film_900` preset and configurable treatment of title/credit time.
- Added separate persisted scenes, independent shots, structured continuity, storyboard and
  character-reference assets, explicit TTS/recorded dialogue choice, and optimistic revisions.
- Added fingerprint-bound approvals for Telugu script, pronunciation, identity workflow, voice,
  storyboard, rough cut, visual performance, lip-sync, adjacent-shot continuity, staged real-media
  acceptance, and final sound.
- Added dependency gates so final footage follows the approved audio/storyboard rough cut and real
  acceptance follows 90 seconds, 180 seconds, then 900 seconds.
- Added regression coverage showing that a changed shot invalidates only that shot's current
  approval while unrelated approved assets remain reusable.
- No real-media acceptance run, FFmpeg rough render, qualified Telugu voice model, qualified
  reference-driven generator, or lip-sync runtime is claimed by Phase 2C.

## Reference-driven addendum Phase 1 evidence

- Audited the current checkout and retained the existing React/Vite, FastAPI, PostgreSQL, durable
  queue, local storage ports, worker boundary, `/api/v1` quick generation, and `/api/v2` projects.
- Added ADR-007 and Reference Library v1 before the cross-cutting schema/API changes.
- Extended the canonical media asset abstraction with database-enforced `project` versus `library`
  scope; existing rows migrate to project scope without byte copying.
- Added owner-scoped reusable characters, locations, props, and shot references. Editable Unicode
  names/aliases remain display metadata and opaque IDs remain identity/authorization boundaries.
- Added append-only versions for character identity versus wardrobe, location views versus lighting,
  prop variants versus state, and shot references. Each binding captures exact asset ID, asset
  metadata version, SHA-256, role, and optional view label.
- Added optimistic entity renaming, approval of frozen fingerprints, additive typed v2 endpoints,
  and Film Library controls for creating/uploading/versioning/approving records.
- Added the forward-only migration `20261013_0007`, PostgreSQL restart/owner-isolation tests, domain
  and application tests, and frontend workflows.
- Phase 1 did not implement project pins or name resolution; those are delivered by Phase 2 below.
  Composition, I2V, reference-video conditioning, VACE, Animate, automated visual identity scoring,
  and real continuity acceptance remain later phases.

## Reference-driven addendum Phase 2 evidence

- Added ADR-008 and updated Reference Library v1 before changing schema and `/api/v2`.
- Added append-only project Film Bible snapshots with exact approved entity/version IDs, typed
  roles, version numbers, fingerprints, approval state, and owner/project scoping.
- Added Unicode-safe exact English/Telugu display-name and alias resolution within one approved
  snapshot. Ambiguous and unresolved names remain explicit; a rename retains the opaque identity.
- Added append-only shot-binding revisions tied to the exact film shot version and Film Bible
  snapshot, plus latest-binding affected-shot reporting.
- Added Project Film Bible controls for explicit pin selection, approval, selective draft adoption,
  mention resolution, shot selection, and affected-shot inspection. The UI does not claim visual
  identity or continuity merely because references were selected.
- Added migration `20261013_0008`, PostgreSQL restart coverage, domain/application regressions, route
  coverage, and frontend interaction tests. Offline Python and frontend checks pass; PostgreSQL
  integration execution remains pending because no test database was configured in this run.
- Real I2V, reference-video inspection/conditioning, VACE, Animate, and real continuity acceptance
  remain unimplemented and unclaimed.

## Reference-driven addendum Phase 3 evidence

- Added ADR-009 and Starting-frame Composition Contract v1 before the schema and API changes.
- Added immutable per-shot composition revisions for composed uploads or ordered background,
  character, prop and overlay layers. Revisions pin the exact shot binding, source and mask asset
  version/hash, optional library-version provenance, source-pixel crop, destination rectangle,
  fit, rotation, opacity, canvas, output-rights declaration, visible speaker and shot-intent notes.
- Added a replaceable renderer port and pinned Pillow 11.3.0 adapter. It validates source hashes and
  image limits, preserves RGBA, applies same-size manual masks, never mirrors implicitly, and emits
  deterministic PNG bytes. Automatic segmentation and harmonization are visibly unsupported.
- Added draft, rendered and approved lifecycle states. Render publication inserts the output media
  asset and advances the composition in one database transaction, with stored-file cleanup if the
  transaction fails. Approval rechecks and pins the exact output asset version and SHA-256.
- Added additive create/list/render/preview/approve endpoints, authoritative server-preview UI,
  migration `20261013_0009`, and deterministic regression tests. Offline verification completed
  with 117 passed and 12 PostgreSQL tests skipped, strict mypy over 75 source files, clean Ruff,
  77 frontend tests, strict TypeScript/ESLint/Prettier, and a production frontend build.
- PostgreSQL integration and migration execution remains pending because Docker/test database access
  was unavailable. No GPU, I2V, automatic photorealistic composition, or real-media acceptance is
  claimed by Phase 3.

## Reference-driven addendum Phase 4 evidence

- Added ADR-010 plus explicit image-generation and Wan2.2 runtime specifications before completing
  the cross-layer implementation.
- Extended the canonical request, job, durable queue, worker and result lifecycle with immutable
  approved-image manifests and measured conditioning evidence; no second job state model was added.
- Added the isolated external Wan2.2 TI2V-5B adapter pinned to code commit
  `1ea34ff48f87168174e12956e200b1d908b1c5ff` and model revision
  `921dbaf3f1674a56f47e83fb80a34bac8a8f203e`. It verifies source hashes, normalizes deterministic
  RGB PNG input, always supplies `--image`, checks GPU/disk availability, validates generated media,
  and cleans subprocess trees and derivatives on cancellation/failure.
- Added owner-scoped idempotency, exact backend routing, additive shot-scoped `/api/v2` operations,
  browser-safe string seeds, and approved-composition UI controls. `/api/v1` remains T2V-only.
- Added migration `20261013_0010`, CPU input-plumbing regressions, and an explicit two-input plus
  cancellation GPU qualification harness. The harness was not executed here, so the runtime remains
  disabled and no real-media or identity-continuity acceptance is claimed.

## Reference-driven addendum Phase 5 evidence

- Added ADR-011 and Reference-video Guidance Contract v1 before the schema and API changes.
- Added append-only per-shot guidance revisions that pin the current shot and binding revisions,
  inspected asset metadata version/hash, verified inspector revision, measured duration/dimensions/
  frame rate, optional exact library provenance, purpose, trim, notes, and content fingerprint.
- Enforced 250–30,000 ms trims inside measured source duration. Library sources must belong to an
  approved version pinned by the shot and their approved role must match the selected purpose.
- Added owner-scoped source preview and separate approval routes. The browser seeks to and stops at
  the persisted trim; replacing a range creates a later revision and preserves earlier approvals.
- Added verified inspection for reusable library media through the existing inspector, migration
  `20261013_0011`, application/domain/API/UI tests, and Film Library/Project controls.
- This phase does not transcode a derivative clip, run VACE/Animate, prove identity or emotional
  acting, or satisfy any 90/180/900-second real-media acceptance gate.

## Reference-driven addendum Phase 6 evidence

- Added ADR-012 and Controlled-video Runtime Contract v1 before finalizing the public/runtime
  behavior. The existing queue, job states, worker boundary, artifact store, and image-conditioned
  request remain canonical.
- Added explicit VACE performance-transfer, Wan Animate character-animation, and Wan Animate
  replacement operations. Each freezes the approved starting frame, approved bounded guidance,
  exact shared shot binding, provider revision, operation, trim, source hashes, and deterministic
  constraint-plan fingerprint.
- Added fail-closed conflict checks: non-performance purposes cannot become model inputs; VACE
  requires the selected starting-frame environment; Animate rejects separately selected
  location/lighting/prop constraints and requires an associated visible character.
- Added isolated pinned adapters for VACE code/model revisions
  `48eb44f1c4be87cc65a98bff985a26976841e9f3` /
  `c76cda849bfb74d563b95f3db039421e9df2a570` and Wan2.2-Animate revisions
  `29d4a35d32273d5309a3a95250bd4e118d8789b2` /
  `cb93a225fbaf1ca100f54e79da8f994995b689b3`.
- Runtime startup verifies clean code, checkpoint-tree digest, exact FFmpeg digest/version, report
  evidence, and resource thresholds. Worker execution validates both source hashes, creates a
  bounded exact trim, preserves operation-specific input roles, records derivative/control hashes,
  and removes the per-run workspace on success, cancellation, or failure.
- Added provider discovery/submission APIs and an explicit browser opt-in panel that shows disabled
  runtimes and environment tradeoffs. No automatic provider selection or fallback is performed.
- Added migration `20261013_0012`, offline application/backend/config/frontend regressions, and an
  opt-in target-GPU qualification harness. The harness was not run, so visual performance,
  identity, emotion, continuity, lip-sync, sound, and all 90/180/900-second gates remain unverified.

## Reference-driven addendum Phase 7A evidence

- Added ADR-013 and extended Media Runtime v1 before changing persistence and the additive v2 API.
- Added an immutable 900-second rough-cut manifest to the canonical generation request and durable
  job lifecycle. It freezes current scene/shot revisions, workspace and manifest fingerprints, and
  exact approved storyboard and recorded-dialogue asset versions, hashes, and opaque storage keys.
- Submission requires the Telugu preset, an exact 1280x720 at 24 fps export profile, complete scene
  and shot timing, current Telugu-script/pronunciation approvals, and current storyboard and voice-
  performance approvals. TTS remains unsupported in this phase and is rejected explicitly.
- Added a pinned FFmpeg/ffprobe adapter using fixed no-shell argument arrays. It hashes every input,
  renders independent shot intermediates, concatenates the homogeneous outputs, measures the final
  resolution/frame count/duration, reports only confirmed shot progress, and removes temporary data
  on success, cancellation, and failure.
- Added scoped provider/submit/status/cancel/output operations, browser controls, migration
  `20261013_0013`, and an opt-in real-media qualification harness. The harness was collected but not
  executed here, so the runtime remains disabled and no rough-cut quality or film acceptance is
  claimed. Final footage, Telugu TTS, lip-sync, final mix, and 90/180/900-second acceptance remain.

## Reference-driven addendum Phase 7B implementation evidence

- Added ADR-014 and the additive read-only film-readiness API before implementation. Readiness is
  recomputed from the project contract, current scene/shot fingerprints, and current approvals; it
  does not create a second workflow state or database migration.
- Added deterministic ordered adjacent-shot boundaries. Cross-scene boundaries enumerate changes
  to location, lighting, wardrobe, props, physical state, and character positions while keeping
  artistic approval explicitly human-owned and project-wide for the current edit.
- Added structural timing blockers, current missing approvals, actionable gate flags, and the next
  project gate to the browser review panel. The browser consumes server-authoritative readiness and
  never infers acceptance from duration.
- Final-sound approval now requires inspected audio-bearing evidence whose measured duration covers
  the 900-second project target after the current film milestone.
- Added offline house/temple, one-shot replacement, restart derivation, API/client, and browser
  regressions. PostgreSQL execution and authorized real house/temple media remain pending, so no
  90/180/900-second or film-quality acceptance is claimed.

## 2026-10-16 RunPod deployment and recovery evidence

| Code | Automated tests | Runtime configured | Real media/GPU verified |
| --- | --- | --- | --- |
| Implemented: full-SHA bootstrap/install, Supervisor, loopback PostgreSQL/API/Nginx, userspace Tailscale Serve, status/doctor/logs, explicit update, consistent backup, guarded restore, fake smoke test, credential rotation | Local pass: Ruff format/lint, strict mypy over 114 files, 186 Python tests passed; 16 environment tests skipped and 3 GPU tests deselected. Frontend Prettier/ESLint/typecheck, 87 tests, and production build passed. Bash syntax passed; ShellCheck is enforced in CI. | Not configured on a RunPod in this environment. Pod boot integration is explicitly `NOT_CONFIGURED`; Tailscale login/Serve/TLS and PostgreSQL package installation need disposable-Pod verification. | No. Demo remains `VIDEO_APP_BACKEND=fake`; no model weights, CUDA job, Telugu media, or 90/180/900-second acceptance was run. |

The deployment unit suite covers strict literal configuration, special-character database
passwords, stale terminal database URL replacement, repeated install/start preservation, one worker,
foreign port refusal, Supervisor/Nginx boundaries, exact Vite hostname allowlisting, distinct
Tailscale daemon/login states, secret redaction, archive traversal/link rejection, checksum
validation, and sample-media recovery. These offline checks do not substitute for a clean Ubuntu
RunPod install, a real PostgreSQL restore rehearsal, or external Tailscale browser evidence.
