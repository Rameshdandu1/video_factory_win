from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pytest
from PIL import Image

from video_app.application.library import StartingFrameRenderError
from video_app.domain.assets import AssetScope, RightsDeclaration
from video_app.domain.library import (
    CompositionAssetSnapshot,
    CompositionFit,
    CompositionLayerRole,
    LayerTransform,
    StartingFrameComposition,
    StartingFrameLayer,
    StartingFrameMode,
)
from video_app.infrastructure.media import PillowStartingFrameRenderer

NOW = datetime(2026, 10, 13, tzinfo=timezone.utc)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _snapshot(asset_id: str, path: Path) -> CompositionAssetSnapshot:
    return CompositionAssetSnapshot(
        asset_id=asset_id,
        asset_version=1,
        asset_sha256=_sha(path),
        scope=AssetScope.PROJECT,
    )


def _composition(
    source: CompositionAssetSnapshot, mask: CompositionAssetSnapshot
) -> StartingFrameComposition:
    return StartingFrameComposition.create(
        composition_id="composition_pixels",
        project_id="project_one",
        owner_id="owner_one",
        shot_id="shot_one",
        shot_version=1,
        shot_binding_revision_id="binding_one",
        revision=1,
        mode=StartingFrameMode.LAYERED,
        canvas_width=64,
        canvas_height=64,
        background_rgba="#00000000",
        output_rights=RightsDeclaration.OWNED,
        framing_notes="",
        pose_notes="",
        action_notes="",
        lighting_notes="",
        visible_speaker_entity_id=None,
        layers=(
            StartingFrameLayer(
                role=CompositionLayerRole.BACKGROUND,
                source=source,
                mask=mask,
                transform=LayerTransform(
                    x=0,
                    y=0,
                    width=2,
                    height=1,
                    rotation_millidegrees=0,
                    opacity_basis_points=10_000,
                    fit=CompositionFit.STRETCH,
                ),
            ),
        ),
        now=NOW,
    )


@pytest.mark.anyio
async def test_renderer_is_deterministic_preserves_order_alpha_and_mask(tmp_path: Path) -> None:
    source_path = tmp_path / "source.png"
    source = Image.new("RGBA", (2, 1))
    source.putdata([(255, 0, 0, 255), (0, 0, 255, 128)])
    source.save(source_path, format="PNG")
    mask_path = tmp_path / "mask.png"
    mask = Image.new("RGBA", (2, 1))
    mask.putdata([(255, 255, 255, 255), (0, 0, 0, 255)])
    mask.save(mask_path, format="PNG")
    composition = _composition(
        _snapshot("asset_source", source_path),
        _snapshot("asset_mask", mask_path),
    )
    renderer = PillowStartingFrameRenderer(tmp_path)

    first = await renderer.render(
        composition, {"asset_source": source_path, "asset_mask": mask_path}
    )
    second = await renderer.render(
        composition, {"asset_source": source_path, "asset_mask": mask_path}
    )

    assert _sha(first) == _sha(second)
    with Image.open(first) as rendered:
        assert rendered.mode == "RGBA"
        assert rendered.size == (64, 64)
        assert rendered.getpixel((0, 0)) == (255, 0, 0, 255)
        assert rendered.getpixel((1, 0))[3] == 0


@pytest.mark.anyio
async def test_renderer_rejects_changed_source_bytes(tmp_path: Path) -> None:
    source_path = tmp_path / "source.png"
    Image.new("RGBA", (2, 1), (255, 0, 0, 255)).save(source_path, format="PNG")
    mask_path = tmp_path / "mask.png"
    Image.new("RGBA", (2, 1), (255, 255, 255, 255)).save(mask_path, format="PNG")
    composition = _composition(
        _snapshot("asset_source", source_path),
        _snapshot("asset_mask", mask_path),
    )
    Image.new("RGBA", (2, 1), (0, 255, 0, 255)).save(source_path, format="PNG")

    with pytest.raises(StartingFrameRenderError, match="checksum"):
        await PillowStartingFrameRenderer(tmp_path).render(
            composition,
            {"asset_source": source_path, "asset_mask": mask_path},
        )
