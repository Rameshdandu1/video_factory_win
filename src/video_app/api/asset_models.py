"""HTTP representations for immutable project assets."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from video_app.domain.assets import AssetKind, AssetScope, AssetState, MediaAsset, RightsDeclaration


class MediaMetadataModel(BaseModel):
    format_name: str
    duration_ms: int
    width: int | None
    height: int | None
    frame_rate_numerator: int | None
    frame_rate_denominator: int | None
    sample_rate: int | None
    channels: int | None
    sample_count: int | None


class MediaAssetModel(BaseModel):
    id: str
    project_id: str | None
    scope: AssetScope
    version: int
    kind: AssetKind
    state: AssetState
    original_filename: str
    media_type: str
    size_bytes: int
    sha256: str
    rights: RightsDeclaration
    created_at: datetime
    metadata: MediaMetadataModel | None
    inspector_revision: str | None
    inspected_at: datetime | None

    @classmethod
    def from_domain(cls, asset: MediaAsset) -> MediaAssetModel:
        return cls(
            id=asset.id,
            project_id=asset.project_id,
            scope=asset.scope,
            version=asset.version,
            kind=asset.kind,
            state=asset.state,
            original_filename=asset.original_filename,
            media_type=asset.media_type,
            size_bytes=asset.size_bytes,
            sha256=asset.sha256,
            rights=asset.rights,
            created_at=asset.created_at,
            metadata=(
                MediaMetadataModel(
                    format_name=asset.metadata.format_name,
                    duration_ms=asset.metadata.duration_ms,
                    width=asset.metadata.width,
                    height=asset.metadata.height,
                    frame_rate_numerator=asset.metadata.frame_rate_numerator,
                    frame_rate_denominator=asset.metadata.frame_rate_denominator,
                    sample_rate=asset.metadata.sample_rate,
                    channels=asset.metadata.channels,
                    sample_count=asset.metadata.sample_count,
                )
                if asset.metadata is not None
                else None
            ),
            inspector_revision=asset.inspector_revision,
            inspected_at=asset.inspected_at,
        )


class MediaAssetListModel(BaseModel):
    items: tuple[MediaAssetModel, ...]
