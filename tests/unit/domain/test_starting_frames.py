from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from video_app.domain.assets import AssetScope, RightsDeclaration
from video_app.domain.library import (
    CompositionAssetSnapshot,
    CompositionFit,
    CompositionLayerRole,
    LayerTransform,
    StartingFrameComposition,
    StartingFrameLayer,
    StartingFrameMode,
    StartingFrameStatus,
)
from video_app.domain.models import DomainValidationError

NOW = datetime(2026, 10, 13, tzinfo=timezone.utc)
SHA = "a" * 64


def _layer(role: CompositionLayerRole = CompositionLayerRole.BACKGROUND) -> StartingFrameLayer:
    return StartingFrameLayer(
        role=role,
        source=CompositionAssetSnapshot(
            asset_id="asset_source",
            asset_version=1,
            asset_sha256=SHA,
            scope=AssetScope.PROJECT,
        ),
        transform=LayerTransform(
            x=0,
            y=0,
            width=832,
            height=480,
            rotation_millidegrees=0,
            opacity_basis_points=10_000,
            fit=CompositionFit.COVER,
        ),
    )


def _composition(
    *, mode: StartingFrameMode = StartingFrameMode.LAYERED
) -> StartingFrameComposition:
    role = (
        CompositionLayerRole.STARTING_FRAME
        if mode is StartingFrameMode.COMPOSED_UPLOAD
        else CompositionLayerRole.BACKGROUND
    )
    return StartingFrameComposition.create(
        composition_id="composition_one",
        project_id="project_one",
        owner_id="owner_one",
        shot_id="shot_one",
        shot_version=2,
        shot_binding_revision_id="binding_one",
        revision=1,
        mode=mode,
        canvas_width=832,
        canvas_height=480,
        background_rgba="#00000000",
        output_rights=RightsDeclaration.OWNED,
        framing_notes="Wide two-shot",
        pose_notes="Arjun faces Sita",
        action_notes="Sita raises the letter",
        lighting_notes="Warm practical light",
        visible_speaker_entity_id="character_sita",
        layers=(_layer(role),),
        now=NOW,
    )


def test_composition_fingerprint_pins_transform_source_and_binding_revision() -> None:
    original = _composition()
    repeated = _composition()
    changed_layer = replace(
        original.layers[0],
        transform=replace(original.layers[0].transform, x=10),
    )
    changed = StartingFrameComposition.create(
        composition_id="composition_two",
        project_id=original.project_id,
        owner_id=original.owner_id,
        shot_id=original.shot_id,
        shot_version=original.shot_version,
        shot_binding_revision_id=original.shot_binding_revision_id,
        revision=original.revision,
        mode=original.mode,
        canvas_width=original.canvas_width,
        canvas_height=original.canvas_height,
        background_rgba=original.background_rgba,
        output_rights=original.output_rights,
        framing_notes=original.framing_notes,
        pose_notes=original.pose_notes,
        action_notes=original.action_notes,
        lighting_notes=original.lighting_notes,
        visible_speaker_entity_id=original.visible_speaker_entity_id,
        layers=(changed_layer,),
        now=NOW,
    )
    assert original.fingerprint == repeated.fingerprint
    assert changed.fingerprint != original.fingerprint


def test_render_and_approval_pin_exact_output_hash() -> None:
    draft = _composition(mode=StartingFrameMode.COMPOSED_UPLOAD)
    rendered = draft.with_rendered_asset(
        asset_id="asset_rendered",
        asset_version=1,
        asset_sha256="b" * 64,
        renderer_revision="pillow-11.3.0/composition-v1",
        now=NOW,
    )
    approved = rendered.approve(now=NOW)
    assert draft.status is StartingFrameStatus.DRAFT
    assert rendered.status is StartingFrameStatus.RENDERED
    assert approved.status is StartingFrameStatus.APPROVED
    assert approved.rendered_sha256 == "b" * 64
    with pytest.raises(RuntimeError):
        approved.approve(now=NOW)


def test_composed_upload_mode_rejects_multiple_or_mislabelled_layers() -> None:
    with pytest.raises(DomainValidationError):
        StartingFrameComposition.create(
            composition_id="composition_invalid",
            project_id="project_one",
            owner_id="owner_one",
            shot_id="shot_one",
            shot_version=1,
            shot_binding_revision_id="binding_one",
            revision=1,
            mode=StartingFrameMode.COMPOSED_UPLOAD,
            canvas_width=832,
            canvas_height=480,
            background_rgba="#000000ff",
            output_rights=RightsDeclaration.OWNED,
            framing_notes="",
            pose_notes="",
            action_notes="",
            lighting_notes="",
            visible_speaker_entity_id=None,
            layers=(_layer(),),
            now=NOW,
        )
