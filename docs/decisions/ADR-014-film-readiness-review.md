# ADR-014: Derived film readiness and continuity review

Status: Accepted on 2026-10-13

## Context

The Telugu short-film workflow persists versioned scenes, shots, continuity fields, and
fingerprint-bound approvals. Operators still need one authoritative view that explains which
current approvals are missing, which adjacent shots require continuity review, and whether the edit
may advance to the next real-media gate. Persisting a second readiness state would drift from those
canonical records and make restart recovery less reliable.

Final-sound approval also needs to prove that its evidence was inspected and contains a measured
audio stream for the complete target duration. Accepting an uninspected audio/video filename would
not satisfy the production contract.

## Decision

- Derive readiness on demand from the current project contract fingerprint, scene and shot content
  fingerprints, and persisted approvals. Readiness is not stored and introduces no new queue,
  persistence abstraction, or schema.
- Order scenes and shots by their explicit positions, then derive every adjacent-shot boundary.
  Each boundary identifies both subjects, whether it crosses a scene, which structured continuity
  fields change, and a deterministic fingerprint. The existing project-wide
  `adjacent_shot_continuity` approval remains bound to the complete current edit.
- Report structural blockers, current missing approvals, actionable gate flags, the next project
  gate, and final acceptance separately. A measured duration never substitutes for approval.
- Add one owner-scoped, read-only `/api/v2/projects/{project_id}/film/readiness` representation and
  render that representation in the browser. The browser does not reproduce readiness rules.
- Require final-sound evidence to be an inspected audio or video asset with complete positive audio
  metadata and measured duration at least equal to the project target.
- Preserve restart behavior by recomputing from PostgreSQL after every process start. A changed
  scene or shot invalidates only approvals whose current subject or workspace fingerprint changed.

## Consequences

Readiness is deterministic and cannot become stale independently of the source records. Existing
approval rows and deployed schemas remain compatible. The view can identify continuity transitions
but does not itself judge their artistic quality; a reviewer must still approve real evidence for
the complete edit. Evidence approvals continue to pin the current asset ID under the existing
schema, so immutable asset-version evidence binding remains a future schema-controlled change.
