# ADR-009: Starting-frame composer and approval gate

Status: Accepted

Date: 2026-10-13

## Context

Reference-driven generation needs a reproducible starting image for each shot. A browser-only
canvas, mutable asset references, or a seed is not sufficient provenance. The application must
support both an already-composed image and a layered composition while keeping Wan2.1 behind the
existing backend boundary.

## Decision

- Store immutable starting-frame composition revisions per film shot.
- Pin the exact shot-binding revision and exact source/mask asset versions and SHA-256 hashes.
- Model layer order, source-pixel crop, destination rectangle, fit mode, rotation and opacity as
  structured data. Mirroring is not supported in v1, so it cannot happen implicitly.
- Rasterize on the server through a replaceable `StartingFrameRenderer` application port. The v1
  adapter uses pinned Pillow and emits an RGBA PNG with deterministic settings.
- Publish a rasterized image through the existing artifact store and media-asset table. Database
  publication of the asset and composition transition occurs in one transaction; failed database
  publication removes the stored file.
- The browser displays the server-rendered PNG as its authoritative preview. It does not maintain
  a second rendering algorithm.
- Approval is a distinct transition that pins the output asset version/hash, renderer revision,
  composition fingerprint and shot-binding revision.
- Future I2V orchestration must require an approved composition revision. This ADR does not add an
  I2V provider or claim that manual layering produces photorealistic harmonization.

## Consequences

- One forward-only migration adds composition revision and layer tables.
- New additive `/api/v2` routes create, list, render, preview and approve compositions.
- Source assets remain owner-scoped; reusable library assets are accepted only when they belong to
  an exact version pinned by the selected shot-binding revision.
- Automatic segmentation and harmonization remain explicit future capabilities. Manual PNG alpha
  and uploaded masks are supported now.
- A new revision is required for edits; an approved revision is never mutated.
