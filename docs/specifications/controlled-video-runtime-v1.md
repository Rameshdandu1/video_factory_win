# Controlled-video Runtime Contract v1

Status: Implemented; runtimes disabled pending target-GPU qualification

## Supported operations

| Provider ID | Operation | Pinned task | Frozen inputs | Environment rule |
| --- | --- | --- | --- | --- |
| `vace-performance-transfer` | `vace_performance_transfer` | `animate_anything` / `salientbboxtrack` | approved frame plus approved trimmed driving video | approved starting-frame environment is required |
| `wan-animate-character` | `animate_character` | `animate-14B` with retarget preprocessing | approved reference image plus approved trimmed driving video | driving-video environment; separate set/prop pins are rejected |
| `wan-animate-replacement` | `animate_replacement` | `animate-14B` with replacement preprocessing | approved replacement image plus approved trimmed driving video | driving-video environment; separate set/prop pins are rejected |

Only `motion_performance` guidance is accepted. The job must pin the current approved composition,
approved guidance, current shot, and exact shared shot-binding revision. The reference range must be
inside the provider's qualified duration. Unsupported purposes or conflicting constraints return
`CONSTRAINT_CONFLICT`; nothing is silently removed.

## Immutable job manifest

The existing image-conditioned request stores the starting-frame source ID/version/SHA-256,
composition revision/fingerprint, shot revision, required backend/revision, and whole-manifest
fingerprint. Controlled jobs additionally store:

- guidance ID/revision/fingerprint and purpose;
- reference asset ID/version/SHA-256/storage key and exact millisecond trim;
- explicit controlled operation and environment-preservation choice;
- deterministic constraint-plan fingerprint.

Success requires measured evidence for the exact starting-frame source and normalized derivative,
the exact reference source and trimmed derivative, and a deterministic fingerprint of the generated
control files. A successful controlled job without complete evidence is invalid.

## Process boundary

Each runtime executes only in the worker. It verifies a clean exact upstream Git revision, the
qualified checkpoint-tree digest, and an exact FFmpeg executable digest/version before accepting
work. It uses an allowlisted child environment with model-network access disabled, no shell, a
bounded deadline, GPU/disk preflight, process-group cancellation, and temporary-file cleanup.

The VACE adapter invokes the pinned pipeline with distinct `--image` and `--video` inputs and a
private control directory. The Wan Animate adapter invokes pinned preprocessing with distinct
`--refer_path` and `--video_path`; character animation uses `--retarget_flag`, while replacement
uses `--replace_flag`. Generated output must decode to the qualified frame count and resolution.

## Qualification report

A runtime is discoverable as enabled only when its configuration and JSON report match all fields:

- `status: approved`, exact code/model/task/checkpoint pins;
- exact shared FFmpeg SHA-256 and first version line;
- exact ordered operations;
- `starting_frame_conditioning_verified`, `reference_video_trim_verified`,
  `constraint_plan_verified`, `control_derivatives_verified`, and
  `cancellation_cleanup_verified`, all `true`;
- positive measured `minimum_free_disk_bytes` and `minimum_free_vram_bytes`.

Qualification is operator evidence from the authorized target GPU. Offline tests do not create an
approved report, download weights, enable a provider, or assert real-media quality.

## Additive API

- `GET /api/v2/controlled-generation/providers`
- `POST /api/v2/projects/{project_id}/film/shots/{shot_id}/starting-frames/{composition_id}/reference-guidance/{guidance_id}/generations`

Submission uses a provider ID, prompt, browser-safe string seed or null, stable idempotency key, and
explicit `preserve_environment`. Existing image-job status, cancellation, and output routes apply.
