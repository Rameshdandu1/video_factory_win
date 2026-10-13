# ADR-010: Isolated Wan2.2 TI2V image-generation adapter

Status: Accepted

Date: 2026-10-13

## Context

Approved starting-frame revisions now provide reproducible source pixels, but the existing Wan2.1
text-to-video adapter cannot truthfully provide reference-driven generation. Wan2.2 TI2V-5B can
condition generation on an image. Its code, model, hardware behavior, and output geometry are a
separate runtime contract and must not alter Generation Contract v1.

## Decision

- Add image-to-video to the canonical generation request and job lifecycle. Do not add a second
  queue, job state model, persistence abstraction, or worker.
- Keep Wan2.2 behind a dedicated `backends/wan22/` adapter. It is the only package allowed to
  invoke the external Wan2.2 checkout.
- Pin the external checkout to commit `1ea34ff48f87168174e12956e200b1d908b1c5ff` and the
  `Wan-AI/Wan2.2-TI2V-5B` checkpoint to revision
  `921dbaf3f1674a56f47e83fb80a34bac8a8f203e`.
- Accept image-to-video work only from an approved starting-frame composition whose current shot
  revision and rendered asset version/hash still match. Persist that full manifest on the job.
- Route image jobs only to a worker advertising the exact backend and revision in the manifest.
  A missing, unreadable, or hash-mismatched image fails closed; it must never fall back to T2V.
- Resolve opaque storage keys inside the worker, normalize source pixels to deterministic RGB PNG,
  verify that the normalized derivative is supplied through Wan2.2's `--image` argument, and
  persist derivative evidence on success.
- Expose additive `/api/v2` provider and shot-scoped generation operations. Keep `/api/v1/jobs`
  text-to-video only and preserve its wire contract.
- Keep the adapter disabled unless exact pins and a locally signed-off qualification report match.
  GPU tests are explicit opt-in tests and cannot be replaced by duration-only MP4 checks.

## Consequences

- One forward-only migration adds immutable conditioning and derivative-evidence columns to the
  existing generation job table plus owner-scoped idempotency.
- The requested resolution is an upstream area/orientation preset. The actual output dimensions
  are derived from the source aspect ratio using the pinned upstream geometry rule and are recorded
  in the result.
- Normal unit and integration tests remain CPU-only and use fakes or subprocess fixtures; no test
  downloads model weights.
- Image-to-video is unavailable, visibly and safely, until an operator supplies a qualified runtime.
