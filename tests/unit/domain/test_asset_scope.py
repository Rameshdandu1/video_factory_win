from datetime import datetime, timezone

import pytest

from video_app.domain.assets import (
    AssetKind,
    AssetScope,
    AssetState,
    MediaAsset,
    RightsDeclaration,
)
from video_app.domain.models import DomainValidationError


def _asset(*, scope: AssetScope, project_id: str | None) -> MediaAsset:
    return MediaAsset(
        id="asset_1",
        project_id=project_id,
        owner_id="owner_1",
        version=1,
        kind=AssetKind.IMAGE,
        state=AssetState.READY,
        original_filename="arjun.png",
        media_type="image/png",
        storage_key="uploads/asset.png",
        size_bytes=4,
        sha256="a" * 64,
        rights=RightsDeclaration.PERMISSIONED,
        created_at=datetime(2026, 10, 13, tzinfo=timezone.utc),
        scope=scope,
    )


def test_library_asset_has_no_project_boundary() -> None:
    assert _asset(scope=AssetScope.LIBRARY, project_id=None).project_id is None


@pytest.mark.parametrize(
    ("scope", "project_id"),
    [(AssetScope.PROJECT, None), (AssetScope.LIBRARY, "project_1")],
)
def test_asset_scope_and_project_id_cannot_disagree(
    scope: AssetScope, project_id: str | None
) -> None:
    with pytest.raises(DomainValidationError):
        _asset(scope=scope, project_id=project_id)
