# Starting-frame Composition Contract v1

## Purpose

This contract creates an auditable starting image for one film shot. It supports either one
already-composed source image or an ordered set of approved background, character, prop and
overlay layers. It is an editing and approval workflow, not an automatic photorealistic synthesis
claim.

## Revision lifecycle

`draft -> rendered -> approved`

- Creating a revision freezes its canvas, notes, shot-binding revision and source selections.
- Rendering is repeatable for the same inputs and renderer revision and produces an RGBA PNG.
- Approval is allowed only for the current rendered bytes. Approval pins the exact output SHA-256.
- To change a layer, mask, transform, note, canvas or source, create a new revision.

## Canvas and transforms

- Canvas width and height are integers from 64 through 4096; total pixels may not exceed
  16,777,216.
- The canvas background is an explicit eight-digit `#RRGGBBAA` value.
- Each layer records a destination rectangle in canvas pixels, a rotation in degrees, opacity in
  basis points, and one of `contain`, `cover`, or `stretch`.
- An optional crop is recorded in source-image pixels. All four crop values are present together.
- Layer order is the stored list order. Rotation is around the destination rectangle centre.
- Mirroring is unsupported in v1. The renderer must not infer or apply it.
- `contain` may produce transparent letterboxing; `cover` may crop; `stretch` explicitly permits
  aspect-ratio distortion.

## Sources, masks, and provenance

- Every source and optional mask is an image media asset in `ready` state.
- Project assets must belong to the target project.
- Library assets must be part of an exact approved library version pinned by the selected
  shot-binding revision. The composition stores the entity, version and version fingerprint.
- In layered mode, background, character and prop sources must be approved library sources with a
  compatible entity kind. Project images remain valid for composed-upload mode, overlays and manual
  masks.
- Source asset version and SHA-256 are copied into the layer snapshot. Rendering fails if current
  storage bytes no longer match the pin.
- A mask is a same-size image interpreted as luminance multiplied by its alpha channel. Transparent
  source uploads retain their alpha.

## Shot intent and review

Each revision stores framing, pose, action and lighting notes and may identify one visibly speaking
character from the selected shot binding. Reviewers see the exact server-rendered preview,
resolution, fit/crop settings, layer provenance and output hash before approval.

## Generation gate

Production I2V may consume only an approved composition revision. Any future preview exception must
be explicitly labelled preview-only and may not satisfy film acceptance. This contract does not add
I2V execution.

## Deferred capabilities

Automatic segmentation, background removal, harmonization, relighting and multi-reference model
adapters require separately declared capabilities and qualified providers. Their absence is visible
and never silently simulated.
