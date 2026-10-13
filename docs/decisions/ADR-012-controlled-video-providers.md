# ADR-012: Explicit Controlled-video Providers

Status: Accepted
Date: 2026-10-13

## Context

An approved starting frame and approved reference-video range are different inputs. A backend may
use one as appearance/environment and the other as motion, or may retain the driving video's
environment. Treating VACE and Wan2.2-Animate as interchangeable would silently drop Film Bible
constraints and turn an approval into a false identity or continuity claim.

## Decision

- Extend the canonical generation job with one optional frozen reference-video manifest. Do not add
  another job lifecycle, queue, storage abstraction, or API-process model runtime.
- Expose three distinct operations: VACE performance transfer, Wan Animate character animation, and
  Wan Animate character replacement. A job pins exactly one operation and provider revision.
- Accept only current, separately approved starting-frame and reference-guidance revisions that use
  the same current shot-binding revision. Only `motion_performance` guidance is a model input;
  `shot_guidance` and `review_only` are rejected rather than reinterpreted.
- VACE performance transfer requires the approved starting-frame environment and consumes the
  approved frame plus bounded driving-video range. This is a requested constraint, not a claim that
  the model will preserve identity, emotion, or every pixel.
- Wan Animate operations use the driving-video environment. They are rejected when the shot binding
  separately pins a location, lighting variant, prop variant, or prop state, because this adapter
  has no qualified compositing/mask workflow that can honor both. They also require an explicitly
  associated visible character and cannot claim starting-frame environment preservation.
- Persist a deterministic constraint-plan fingerprint and measured hashes for the normalized image,
  trimmed reference video, and provider-produced control directory.
- Keep both runtimes disabled until an operator supplies exact code/model/checkpoint/FFmpeg pins and
  an approved target-GPU qualification report proving both input roles, operation-specific control
  generation, cancellation cleanup, decode, and resource thresholds.

## Consequences

- Migration `20261013_0012` adds nullable controlled-video provenance and evidence to the existing
  generation-job table. Existing text-to-video and still-conditioned jobs retain their meaning.
- The UI lists disabled providers honestly and requires explicit provider, operation, approved frame,
  prompt, idempotency key, and environment choice before one approved shot can be queued.
- Source changes, trim changes, provider changes, constraint changes, or prompt changes alter the
  immutable manifest and cannot reuse an idempotency key silently.
- This phase provides safe plumbing and qualification gates. It does not satisfy visual-performance,
  adjacent-shot continuity, lip-sync, sound-mix, or 90/180/900-second real-media acceptance.

## Rejected alternatives

- Infer a provider from a guidance label: this hides operation semantics and deployment state.
- Allow Animate to ignore pinned sets/props: this violates approved continuity constraints.
- Use seeds or metadata as identity preservation: neither supplies reference pixels to a backend.
- Run preprocessing or model inference in FastAPI: expensive work remains cancellable worker work.
- Enable a runtime because files exist: files alone do not prove their provenance or behavior.
