# ADR-011: Bounded Reference-video Guidance

Status: Accepted
Date: 2026-10-13

## Context

The Film Library can preserve exact video assets and shot bindings, but a worker must not consume an
entire mutable upload or infer why it was selected. A shot needs a small, reviewable time range with
an explicit purpose. Seed reuse, notes, and a video filename do not preserve identity or prove that a
model follows motion, camera, blocking, or performance.

## Decision

- Add immutable reference-video guidance revisions under the existing Film Bible/library ownership.
- Each revision pins the current film-shot version, exact shot-binding revision, exact asset metadata
  version and SHA-256, verified ffprobe revision and measured video metadata, source scope, and exact
  library provenance when the source is reusable.
- Express purpose as one of `motion_performance`, `shot_guidance`, or `review_only`. These values
  describe intended use only; none is an identity-preservation claim.
- Store trim boundaries as integer milliseconds. A trim is at least 250 ms, at most 30,000 ms, starts
  at or after zero, and ends within the measured source duration.
- Reusable video sources must belong to an approved library version pinned by the selected shot
  binding, and their binding role must equal the guidance purpose. Project sources must belong to the
  current project and cannot claim library provenance.
- Serve the exact authorized source through an owner/project/shot-scoped preview route. The browser
  seeks to the persisted trim; it does not create a second edited copy. Approval is an explicit,
  append-only transition for that exact fingerprint after human review.
- Keep downstream VACE/Animate consumption outside this phase. A future adapter must explicitly pin
  an approved guidance revision rather than selecting “latest” implicitly.

## Consequences

- One forward-only migration adds a guidance-revision table; no existing schema meaning changes.
- Verified inspection becomes available to library assets through the existing inspector and asset
  repository, with the same bounded process and optimistic metadata-version update.
- Re-trimming, changing purpose, changing notes, or replacing a source creates another revision.
- The preview endpoint may expose the full authorized source to the same owner even though playback
  starts and ends at the approved range. Server-side derivative clips and transcoding remain future
  work.
- Approval means the exact source/range/purpose was reviewed. It does not prove identity,
  continuity, emotional acting, provider compatibility, or final-film quality.

## Rejected alternatives

- Store only start/end values on a mutable shot: edits would rewrite evidence and break restart
  provenance.
- Accept uninspected video duration supplied by a browser: it is not authoritative.
- Treat a reference-video seed or character label as identity conditioning: it is not source media.
- Add FFmpeg trimming in the API process: that introduces an unqualified media transformation path
  and duplicate artifacts before a consumer requires them.
