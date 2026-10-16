"""PostgreSQL persistence for immutable project media assets."""

from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncEngine

from video_app.domain.assets import (
    AssetKind,
    AssetScope,
    AssetState,
    MediaAsset,
    MediaMetadata,
    RightsDeclaration,
)
from video_app.infrastructure.schema import media_assets


def _row_to_asset(row: RowMapping) -> MediaAsset:
    created_at: datetime = row["created_at"]
    if created_at.tzinfo is None:
        raise ValueError("database asset timestamp must be timezone-aware")
    metadata_value = row["metadata"]
    metadata = MediaMetadata(**metadata_value) if isinstance(metadata_value, dict) else None
    inspected_at: datetime | None = row["inspected_at"]
    return MediaAsset(
        id=row["id"],
        project_id=row["project_id"],
        owner_id=row["owner_id"],
        version=row["version"],
        kind=AssetKind(row["kind"]),
        state=AssetState(row["state"]),
        original_filename=row["original_filename"],
        media_type=row["media_type"],
        storage_key=row["storage_key"],
        size_bytes=row["size_bytes"],
        sha256=row["sha256"],
        rights=RightsDeclaration(row["rights"]),
        created_at=created_at.astimezone(timezone.utc),
        metadata=metadata,
        inspector_revision=row["inspector_revision"],
        inspected_at=(inspected_at.astimezone(timezone.utc) if inspected_at is not None else None),
        scope=AssetScope(row["scope"]),
    )


class PostgresAssetRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def create(self, asset: MediaAsset) -> MediaAsset:
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        media_assets.insert()
                        .values(
                            id=asset.id,
                            project_id=asset.project_id,
                            owner_id=asset.owner_id,
                            scope=asset.scope.value,
                            version=asset.version,
                            kind=asset.kind.value,
                            state=asset.state.value,
                            original_filename=asset.original_filename,
                            media_type=asset.media_type,
                            storage_key=asset.storage_key,
                            size_bytes=asset.size_bytes,
                            sha256=asset.sha256,
                            rights=asset.rights.value,
                            created_at=asset.created_at,
                            metadata=sa.null(),
                            inspector_revision=None,
                            inspected_at=None,
                        )
                        .returning(media_assets)
                    )
                )
                .mappings()
                .one()
            )
        return _row_to_asset(row)

    async def list(self, owner_id: str, project_id: str, *, limit: int) -> tuple[MediaAsset, ...]:
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        sa.select(media_assets)
                        .where(
                            media_assets.c.owner_id == owner_id,
                            media_assets.c.project_id == project_id,
                        )
                        .order_by(media_assets.c.created_at.desc(), media_assets.c.id.desc())
                        .limit(limit)
                    )
                )
                .mappings()
                .all()
            )
        return tuple(_row_to_asset(row) for row in rows)

    async def get(self, owner_id: str, project_id: str, asset_id: str) -> MediaAsset:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        sa.select(media_assets).where(
                            media_assets.c.owner_id == owner_id,
                            media_assets.c.project_id == project_id,
                            media_assets.c.id == asset_id,
                        )
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            from video_app.application.assets import AssetNotFoundError

            raise AssetNotFoundError(asset_id)
        return _row_to_asset(row)

    async def list_library(self, owner_id: str, *, limit: int) -> tuple[MediaAsset, ...]:
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        sa.select(media_assets)
                        .where(
                            media_assets.c.owner_id == owner_id,
                            media_assets.c.scope == AssetScope.LIBRARY.value,
                        )
                        .order_by(media_assets.c.created_at.desc(), media_assets.c.id.desc())
                        .limit(limit)
                    )
                )
                .mappings()
                .all()
            )
        return tuple(_row_to_asset(row) for row in rows)

    async def get_owner(self, owner_id: str, asset_id: str) -> MediaAsset:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        sa.select(media_assets).where(
                            media_assets.c.owner_id == owner_id,
                            media_assets.c.id == asset_id,
                        )
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            from video_app.application.assets import AssetNotFoundError

            raise AssetNotFoundError(asset_id)
        return _row_to_asset(row)

    async def update(self, asset: MediaAsset, *, expected_version: int) -> MediaAsset:
        metadata: object = sa.null()
        if asset.metadata is not None:
            metadata = {
                "format_name": asset.metadata.format_name,
                "duration_ms": asset.metadata.duration_ms,
                "width": asset.metadata.width,
                "height": asset.metadata.height,
                "frame_rate_numerator": asset.metadata.frame_rate_numerator,
                "frame_rate_denominator": asset.metadata.frame_rate_denominator,
                "sample_rate": asset.metadata.sample_rate,
                "channels": asset.metadata.channels,
                "sample_count": asset.metadata.sample_count,
            }
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        media_assets.update()
                        .where(
                            media_assets.c.id == asset.id,
                            media_assets.c.owner_id == asset.owner_id,
                            media_assets.c.project_id == asset.project_id,
                            media_assets.c.scope == asset.scope.value,
                            media_assets.c.version == expected_version,
                        )
                        .values(
                            version=asset.version,
                            state=asset.state.value,
                            metadata=metadata,
                            inspector_revision=asset.inspector_revision,
                            inspected_at=asset.inspected_at,
                        )
                        .returning(media_assets)
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            from video_app.application.projects import ProjectRevisionConflictError

            raise ProjectRevisionConflictError("asset revision is stale")
        return _row_to_asset(row)
