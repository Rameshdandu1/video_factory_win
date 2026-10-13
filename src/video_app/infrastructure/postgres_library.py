"""PostgreSQL persistence for reusable owner-scoped film-library records."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from video_app.application.library import (
    FilmBibleSnapshotNotFoundError,
    LibraryEntityNotFoundError,
    LibraryRevisionConflictError,
    LibraryVersionNotFoundError,
    ReferenceVideoGuidanceNotFoundError,
    ShotBindingRevisionNotFoundError,
    StartingFrameCompositionNotFoundError,
)
from video_app.domain.assets import AssetScope, MediaAsset, RightsDeclaration
from video_app.domain.library import (
    CompositionAssetSnapshot,
    CompositionFit,
    CompositionLayerRole,
    FilmBiblePin,
    FilmBiblePinRole,
    FilmBibleSnapshot,
    FilmBibleStatus,
    LayerTransform,
    LibraryAssetBinding,
    LibraryEntity,
    LibraryEntityKind,
    LibraryVersion,
    LibraryVersionKind,
    LibraryVersionStatus,
    ReferenceGuidanceStatus,
    ReferenceRole,
    ReferenceVideoGuidance,
    ReferenceVideoPurpose,
    ReferenceVideoSourceSnapshot,
    ShotBindingRevision,
    SourceCrop,
    StartingFrameComposition,
    StartingFrameLayer,
    StartingFrameMode,
    StartingFrameStatus,
)
from video_app.infrastructure.schema import (
    film_bible_pins,
    film_bible_snapshots,
    library_entities,
    library_version_assets,
    library_versions,
    media_assets,
    reference_video_guidance,
    shot_binding_revisions,
    shot_library_bindings,
    starting_frame_compositions,
    starting_frame_layers,
)


def _utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"database {field} timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def _row_to_entity(row: RowMapping) -> LibraryEntity:
    aliases_value: Any = row["aliases"]
    if not isinstance(aliases_value, list) or not all(
        isinstance(alias, str) for alias in aliases_value
    ):
        raise ValueError("database library aliases must be a string list")
    return LibraryEntity(
        id=row["id"],
        owner_id=row["owner_id"],
        kind=LibraryEntityKind(row["kind"]),
        metadata_version=row["metadata_version"],
        display_name=row["display_name"],
        aliases=tuple(aliases_value),
        created_at=_utc(row["created_at"], "created_at"),
        updated_at=_utc(row["updated_at"], "updated_at"),
    )


def _row_to_version(row: RowMapping, bindings: tuple[LibraryAssetBinding, ...]) -> LibraryVersion:
    approved_at: datetime | None = row["approved_at"]
    return LibraryVersion(
        id=row["id"],
        entity_id=row["entity_id"],
        owner_id=row["owner_id"],
        version_number=row["version_number"],
        kind=LibraryVersionKind(row["kind"]),
        status=LibraryVersionStatus(row["status"]),
        label=row["label"],
        notes=row["notes"],
        invariants=row["invariants"],
        state_notes=row["state_notes"],
        voice_profile_id=row["voice_profile_id"],
        rights_statement=row["rights_statement"],
        bindings=bindings,
        fingerprint=row["fingerprint"],
        created_at=_utc(row["created_at"], "created_at"),
        approved_at=_utc(approved_at, "approved_at") if approved_at is not None else None,
    )


def _binding_rows_to_map(
    rows: Iterable[RowMapping],
) -> dict[str, tuple[LibraryAssetBinding, ...]]:
    grouped: dict[str, list[LibraryAssetBinding]] = {}
    for row in rows:
        grouped.setdefault(row["library_version_id"], []).append(
            LibraryAssetBinding(
                asset_id=row["asset_id"],
                asset_version=row["asset_version"],
                asset_sha256=row["asset_sha256"],
                role=ReferenceRole(row["role"]),
                view_label=row["view_label"],
            )
        )
    return {key: tuple(value) for key, value in grouped.items()}


def _film_bible_pin(row: RowMapping) -> FilmBiblePin:
    return FilmBiblePin(
        entity_id=row["entity_id"],
        library_version_id=row["library_version_id"],
        library_version_number=row["library_version_number"],
        version_kind=LibraryVersionKind(row["version_kind"]),
        version_fingerprint=row["version_fingerprint"],
        role=FilmBiblePinRole(row["role"]),
    )


def _row_to_film_bible_snapshot(
    row: RowMapping, pins: tuple[FilmBiblePin, ...]
) -> FilmBibleSnapshot:
    approved_at: datetime | None = row["approved_at"]
    return FilmBibleSnapshot(
        id=row["id"],
        project_id=row["project_id"],
        owner_id=row["owner_id"],
        revision=row["revision"],
        status=FilmBibleStatus(row["status"]),
        pins=pins,
        fingerprint=row["fingerprint"],
        created_at=_utc(row["created_at"], "created_at"),
        approved_at=_utc(approved_at, "approved_at") if approved_at is not None else None,
    )


def _row_to_shot_binding_revision(
    row: RowMapping, bindings: tuple[FilmBiblePin, ...]
) -> ShotBindingRevision:
    return ShotBindingRevision(
        id=row["id"],
        project_id=row["project_id"],
        owner_id=row["owner_id"],
        shot_id=row["shot_id"],
        shot_version=row["shot_version"],
        revision=row["revision"],
        film_bible_snapshot_id=row["film_bible_snapshot_id"],
        bindings=bindings,
        fingerprint=row["fingerprint"],
        created_at=_utc(row["created_at"], "created_at"),
    )


def _composition_asset(row: RowMapping, prefix: str) -> CompositionAssetSnapshot:
    return CompositionAssetSnapshot(
        asset_id=row[f"{prefix}_asset_id"],
        asset_version=row[f"{prefix}_asset_version"],
        asset_sha256=row[f"{prefix}_asset_sha256"],
        scope=AssetScope(row[f"{prefix}_scope"]),
        library_entity_id=row[f"{prefix}_library_entity_id"],
        library_version_id=row[f"{prefix}_library_version_id"],
        library_version_fingerprint=row[f"{prefix}_library_version_fingerprint"],
    )


def _row_to_starting_frame_layer(row: RowMapping) -> StartingFrameLayer:
    crop_values = (row["crop_x"], row["crop_y"], row["crop_width"], row["crop_height"])
    crop = (
        None
        if all(value is None for value in crop_values)
        else SourceCrop(
            x=row["crop_x"],
            y=row["crop_y"],
            width=row["crop_width"],
            height=row["crop_height"],
        )
    )
    return StartingFrameLayer(
        role=CompositionLayerRole(row["role"]),
        source=_composition_asset(row, "source"),
        mask=(_composition_asset(row, "mask") if row["mask_asset_id"] is not None else None),
        transform=LayerTransform(
            x=row["target_x"],
            y=row["target_y"],
            width=row["target_width"],
            height=row["target_height"],
            rotation_millidegrees=row["rotation_millidegrees"],
            opacity_basis_points=row["opacity_basis_points"],
            fit=CompositionFit(row["fit"]),
            crop=crop,
        ),
    )


def _row_to_starting_frame(
    row: RowMapping, layers: tuple[StartingFrameLayer, ...]
) -> StartingFrameComposition:
    rendered_at: datetime | None = row["rendered_at"]
    approved_at: datetime | None = row["approved_at"]
    return StartingFrameComposition(
        id=row["id"],
        project_id=row["project_id"],
        owner_id=row["owner_id"],
        shot_id=row["shot_id"],
        shot_version=row["shot_version"],
        shot_binding_revision_id=row["shot_binding_revision_id"],
        revision=row["revision"],
        mode=StartingFrameMode(row["mode"]),
        status=StartingFrameStatus(row["status"]),
        canvas_width=row["canvas_width"],
        canvas_height=row["canvas_height"],
        background_rgba=row["background_rgba"],
        output_rights=RightsDeclaration(row["output_rights"]),
        framing_notes=row["framing_notes"],
        pose_notes=row["pose_notes"],
        action_notes=row["action_notes"],
        lighting_notes=row["lighting_notes"],
        visible_speaker_entity_id=row["visible_speaker_entity_id"],
        layers=layers,
        fingerprint=row["fingerprint"],
        created_at=_utc(row["created_at"], "created_at"),
        rendered_asset_id=row["rendered_asset_id"],
        rendered_asset_version=row["rendered_asset_version"],
        rendered_sha256=row["rendered_sha256"],
        renderer_revision=row["renderer_revision"],
        rendered_at=_utc(rendered_at, "rendered_at") if rendered_at is not None else None,
        approved_at=_utc(approved_at, "approved_at") if approved_at is not None else None,
    )


def _row_to_reference_video_guidance(row: RowMapping) -> ReferenceVideoGuidance:
    approved_at: datetime | None = row["approved_at"]
    return ReferenceVideoGuidance(
        id=row["id"],
        project_id=row["project_id"],
        owner_id=row["owner_id"],
        shot_id=row["shot_id"],
        shot_version=row["shot_version"],
        shot_binding_revision_id=row["shot_binding_revision_id"],
        revision=row["revision"],
        purpose=ReferenceVideoPurpose(row["purpose"]),
        source=ReferenceVideoSourceSnapshot(
            asset_id=row["source_asset_id"],
            asset_version=row["source_asset_version"],
            asset_sha256=row["source_asset_sha256"],
            media_type=row["source_media_type"],
            scope=AssetScope(row["source_scope"]),
            inspector_revision=row["source_inspector_revision"],
            duration_ms=row["source_duration_ms"],
            width=row["source_width"],
            height=row["source_height"],
            frame_rate_numerator=row["source_frame_rate_numerator"],
            frame_rate_denominator=row["source_frame_rate_denominator"],
            library_entity_id=row["source_library_entity_id"],
            library_version_id=row["source_library_version_id"],
            library_version_fingerprint=row["source_library_version_fingerprint"],
        ),
        trim_start_ms=row["trim_start_ms"],
        trim_end_ms=row["trim_end_ms"],
        guidance_notes=row["guidance_notes"],
        status=ReferenceGuidanceStatus(row["status"]),
        fingerprint=row["fingerprint"],
        created_at=_utc(row["created_at"], "created_at"),
        approved_at=_utc(approved_at, "approved_at") if approved_at is not None else None,
    )


class PostgresLibraryRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def create_entity(self, entity: LibraryEntity) -> LibraryEntity:
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        library_entities.insert()
                        .values(
                            id=entity.id,
                            owner_id=entity.owner_id,
                            kind=entity.kind.value,
                            metadata_version=entity.metadata_version,
                            display_name=entity.display_name,
                            aliases=list(entity.aliases),
                            created_at=entity.created_at,
                            updated_at=entity.updated_at,
                        )
                        .returning(library_entities)
                    )
                )
                .mappings()
                .one()
            )
        return _row_to_entity(row)

    async def get_entity(self, owner_id: str, entity_id: str) -> LibraryEntity:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        sa.select(library_entities).where(
                            library_entities.c.owner_id == owner_id,
                            library_entities.c.id == entity_id,
                        )
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise LibraryEntityNotFoundError(entity_id)
        return _row_to_entity(row)

    async def list_entities(
        self, owner_id: str, *, kind: LibraryEntityKind | None, limit: int
    ) -> tuple[LibraryEntity, ...]:
        query = sa.select(library_entities).where(library_entities.c.owner_id == owner_id)
        if kind is not None:
            query = query.where(library_entities.c.kind == kind.value)
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        query.order_by(
                            library_entities.c.updated_at.desc(), library_entities.c.id.desc()
                        ).limit(limit)
                    )
                )
                .mappings()
                .all()
            )
        return tuple(_row_to_entity(row) for row in rows)

    async def update_entity(self, entity: LibraryEntity, *, expected_version: int) -> LibraryEntity:
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        library_entities.update()
                        .where(
                            library_entities.c.id == entity.id,
                            library_entities.c.owner_id == entity.owner_id,
                            library_entities.c.metadata_version == expected_version,
                        )
                        .values(
                            metadata_version=entity.metadata_version,
                            display_name=entity.display_name,
                            aliases=list(entity.aliases),
                            updated_at=entity.updated_at,
                        )
                        .returning(library_entities)
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise LibraryRevisionConflictError("library metadata revision is stale")
        return _row_to_entity(row)

    async def next_version_number(self, owner_id: str, entity_id: str) -> int:
        await self.get_entity(owner_id, entity_id)
        async with self._engine.connect() as connection:
            value = await connection.scalar(
                sa.select(
                    sa.func.coalesce(sa.func.max(library_versions.c.version_number), 0) + 1
                ).where(
                    library_versions.c.owner_id == owner_id,
                    library_versions.c.entity_id == entity_id,
                )
            )
        if not isinstance(value, int):
            raise RuntimeError("database did not return a library version number")
        return value

    async def create_version(self, version: LibraryVersion) -> LibraryVersion:
        try:
            async with self._engine.begin() as connection:
                row = (
                    (
                        await connection.execute(
                            library_versions.insert()
                            .values(
                                id=version.id,
                                entity_id=version.entity_id,
                                owner_id=version.owner_id,
                                version_number=version.version_number,
                                kind=version.kind.value,
                                status=version.status.value,
                                label=version.label,
                                notes=version.notes,
                                invariants=version.invariants,
                                state_notes=version.state_notes,
                                voice_profile_id=version.voice_profile_id,
                                rights_statement=version.rights_statement,
                                fingerprint=version.fingerprint,
                                created_at=version.created_at,
                                approved_at=version.approved_at,
                            )
                            .returning(library_versions)
                        )
                    )
                    .mappings()
                    .one()
                )
                await connection.execute(
                    library_version_assets.insert(),
                    [
                        {
                            "library_version_id": version.id,
                            "position": position,
                            "asset_id": binding.asset_id,
                            "asset_version": binding.asset_version,
                            "asset_sha256": binding.asset_sha256,
                            "role": binding.role.value,
                            "view_label": binding.view_label,
                        }
                        for position, binding in enumerate(version.bindings)
                    ],
                )
        except IntegrityError as error:
            raise LibraryRevisionConflictError(
                "the library version number was created concurrently; refresh and retry"
            ) from error
        return _row_to_version(row, version.bindings)

    async def _bindings_for(
        self, version_ids: tuple[str, ...]
    ) -> dict[str, tuple[LibraryAssetBinding, ...]]:
        if not version_ids:
            return {}
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        sa.select(library_version_assets)
                        .where(library_version_assets.c.library_version_id.in_(version_ids))
                        .order_by(
                            library_version_assets.c.library_version_id,
                            library_version_assets.c.position,
                        )
                    )
                )
                .mappings()
                .all()
            )
        return _binding_rows_to_map(rows)

    async def get_version(self, owner_id: str, entity_id: str, version_id: str) -> LibraryVersion:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        sa.select(library_versions).where(
                            library_versions.c.owner_id == owner_id,
                            library_versions.c.entity_id == entity_id,
                            library_versions.c.id == version_id,
                        )
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise LibraryVersionNotFoundError(version_id)
        bindings = await self._bindings_for((version_id,))
        return _row_to_version(row, bindings.get(version_id, ()))

    async def list_versions(
        self, owner_id: str, entity_id: str, *, limit: int
    ) -> tuple[LibraryVersion, ...]:
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        sa.select(library_versions)
                        .where(
                            library_versions.c.owner_id == owner_id,
                            library_versions.c.entity_id == entity_id,
                        )
                        .order_by(library_versions.c.version_number.desc())
                        .limit(limit)
                    )
                )
                .mappings()
                .all()
            )
        ids = tuple(row["id"] for row in rows)
        bindings = await self._bindings_for(ids)
        return tuple(_row_to_version(row, bindings.get(row["id"], ())) for row in rows)

    async def approve_version(self, version: LibraryVersion) -> LibraryVersion:
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        library_versions.update()
                        .where(
                            library_versions.c.id == version.id,
                            library_versions.c.owner_id == version.owner_id,
                            library_versions.c.entity_id == version.entity_id,
                            library_versions.c.status == LibraryVersionStatus.DRAFT.value,
                            library_versions.c.fingerprint == version.fingerprint,
                        )
                        .values(
                            status=version.status.value,
                            approved_at=version.approved_at,
                        )
                        .returning(library_versions)
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise LibraryRevisionConflictError("library version is no longer an approvable draft")
        return _row_to_version(row, version.bindings)

    async def next_film_bible_revision(self, owner_id: str, project_id: str) -> int:
        async with self._engine.connect() as connection:
            value = await connection.scalar(
                sa.select(
                    sa.func.coalesce(sa.func.max(film_bible_snapshots.c.revision), 0) + 1
                ).where(
                    film_bible_snapshots.c.owner_id == owner_id,
                    film_bible_snapshots.c.project_id == project_id,
                )
            )
        if not isinstance(value, int):
            raise RuntimeError("database did not return a Film Bible revision")
        return value

    async def create_film_bible_snapshot(self, snapshot: FilmBibleSnapshot) -> FilmBibleSnapshot:
        try:
            async with self._engine.begin() as connection:
                row = (
                    (
                        await connection.execute(
                            film_bible_snapshots.insert()
                            .values(
                                id=snapshot.id,
                                project_id=snapshot.project_id,
                                owner_id=snapshot.owner_id,
                                revision=snapshot.revision,
                                status=snapshot.status.value,
                                fingerprint=snapshot.fingerprint,
                                created_at=snapshot.created_at,
                                approved_at=snapshot.approved_at,
                            )
                            .returning(film_bible_snapshots)
                        )
                    )
                    .mappings()
                    .one()
                )
                await connection.execute(
                    film_bible_pins.insert(),
                    [
                        {
                            "snapshot_id": snapshot.id,
                            "position": position,
                            "entity_id": pin.entity_id,
                            "library_version_id": pin.library_version_id,
                            "library_version_number": pin.library_version_number,
                            "version_kind": pin.version_kind.value,
                            "version_fingerprint": pin.version_fingerprint,
                            "role": pin.role.value,
                        }
                        for position, pin in enumerate(snapshot.pins)
                    ],
                )
        except IntegrityError as error:
            raise LibraryRevisionConflictError(
                "the Film Bible revision was created concurrently; refresh and retry"
            ) from error
        return _row_to_film_bible_snapshot(row, snapshot.pins)

    async def _film_bible_pins_for(
        self, snapshot_ids: tuple[str, ...]
    ) -> dict[str, tuple[FilmBiblePin, ...]]:
        if not snapshot_ids:
            return {}
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        sa.select(film_bible_pins)
                        .where(film_bible_pins.c.snapshot_id.in_(snapshot_ids))
                        .order_by(film_bible_pins.c.snapshot_id, film_bible_pins.c.position)
                    )
                )
                .mappings()
                .all()
            )
        grouped: dict[str, list[FilmBiblePin]] = {}
        for row in rows:
            grouped.setdefault(row["snapshot_id"], []).append(_film_bible_pin(row))
        return {key: tuple(value) for key, value in grouped.items()}

    async def get_film_bible_snapshot(
        self, owner_id: str, project_id: str, snapshot_id: str
    ) -> FilmBibleSnapshot:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        sa.select(film_bible_snapshots).where(
                            film_bible_snapshots.c.id == snapshot_id,
                            film_bible_snapshots.c.owner_id == owner_id,
                            film_bible_snapshots.c.project_id == project_id,
                        )
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise FilmBibleSnapshotNotFoundError(snapshot_id)
        pins = await self._film_bible_pins_for((snapshot_id,))
        return _row_to_film_bible_snapshot(row, pins.get(snapshot_id, ()))

    async def list_film_bible_snapshots(
        self, owner_id: str, project_id: str, *, limit: int
    ) -> tuple[FilmBibleSnapshot, ...]:
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        sa.select(film_bible_snapshots)
                        .where(
                            film_bible_snapshots.c.owner_id == owner_id,
                            film_bible_snapshots.c.project_id == project_id,
                        )
                        .order_by(film_bible_snapshots.c.revision.desc())
                        .limit(limit)
                    )
                )
                .mappings()
                .all()
            )
        ids = tuple(row["id"] for row in rows)
        pins = await self._film_bible_pins_for(ids)
        return tuple(_row_to_film_bible_snapshot(row, pins.get(row["id"], ())) for row in rows)

    async def approve_film_bible_snapshot(self, snapshot: FilmBibleSnapshot) -> FilmBibleSnapshot:
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        film_bible_snapshots.update()
                        .where(
                            film_bible_snapshots.c.id == snapshot.id,
                            film_bible_snapshots.c.owner_id == snapshot.owner_id,
                            film_bible_snapshots.c.project_id == snapshot.project_id,
                            film_bible_snapshots.c.status == FilmBibleStatus.DRAFT.value,
                            film_bible_snapshots.c.fingerprint == snapshot.fingerprint,
                        )
                        .values(
                            status=snapshot.status.value,
                            approved_at=snapshot.approved_at,
                        )
                        .returning(film_bible_snapshots)
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise LibraryRevisionConflictError("Film Bible is no longer an approvable draft")
        return _row_to_film_bible_snapshot(row, snapshot.pins)

    async def next_shot_binding_revision(self, owner_id: str, project_id: str, shot_id: str) -> int:
        async with self._engine.connect() as connection:
            value = await connection.scalar(
                sa.select(
                    sa.func.coalesce(sa.func.max(shot_binding_revisions.c.revision), 0) + 1
                ).where(
                    shot_binding_revisions.c.owner_id == owner_id,
                    shot_binding_revisions.c.project_id == project_id,
                    shot_binding_revisions.c.shot_id == shot_id,
                )
            )
        if not isinstance(value, int):
            raise RuntimeError("database did not return a shot-binding revision")
        return value

    async def create_shot_binding_revision(
        self, revision: ShotBindingRevision
    ) -> ShotBindingRevision:
        try:
            async with self._engine.begin() as connection:
                row = (
                    (
                        await connection.execute(
                            shot_binding_revisions.insert()
                            .values(
                                id=revision.id,
                                project_id=revision.project_id,
                                owner_id=revision.owner_id,
                                shot_id=revision.shot_id,
                                shot_version=revision.shot_version,
                                revision=revision.revision,
                                film_bible_snapshot_id=revision.film_bible_snapshot_id,
                                fingerprint=revision.fingerprint,
                                created_at=revision.created_at,
                            )
                            .returning(shot_binding_revisions)
                        )
                    )
                    .mappings()
                    .one()
                )
                await connection.execute(
                    shot_library_bindings.insert(),
                    [
                        {
                            "binding_revision_id": revision.id,
                            "position": position,
                            "entity_id": binding.entity_id,
                            "library_version_id": binding.library_version_id,
                            "library_version_number": binding.library_version_number,
                            "version_kind": binding.version_kind.value,
                            "version_fingerprint": binding.version_fingerprint,
                            "role": binding.role.value,
                        }
                        for position, binding in enumerate(revision.bindings)
                    ],
                )
        except IntegrityError as error:
            raise LibraryRevisionConflictError(
                "the shot-binding revision was created concurrently; refresh and retry"
            ) from error
        return _row_to_shot_binding_revision(row, revision.bindings)

    async def _shot_bindings_for(
        self, revision_ids: tuple[str, ...]
    ) -> dict[str, tuple[FilmBiblePin, ...]]:
        if not revision_ids:
            return {}
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        sa.select(shot_library_bindings)
                        .where(shot_library_bindings.c.binding_revision_id.in_(revision_ids))
                        .order_by(
                            shot_library_bindings.c.binding_revision_id,
                            shot_library_bindings.c.position,
                        )
                    )
                )
                .mappings()
                .all()
            )
        grouped: dict[str, list[FilmBiblePin]] = {}
        for row in rows:
            grouped.setdefault(row["binding_revision_id"], []).append(_film_bible_pin(row))
        return {key: tuple(value) for key, value in grouped.items()}

    async def list_shot_binding_revisions(
        self, owner_id: str, project_id: str, shot_id: str, *, limit: int
    ) -> tuple[ShotBindingRevision, ...]:
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        sa.select(shot_binding_revisions)
                        .where(
                            shot_binding_revisions.c.owner_id == owner_id,
                            shot_binding_revisions.c.project_id == project_id,
                            shot_binding_revisions.c.shot_id == shot_id,
                        )
                        .order_by(shot_binding_revisions.c.revision.desc())
                        .limit(limit)
                    )
                )
                .mappings()
                .all()
            )
        ids = tuple(row["id"] for row in rows)
        bindings = await self._shot_bindings_for(ids)
        return tuple(
            _row_to_shot_binding_revision(row, bindings.get(row["id"], ())) for row in rows
        )

    async def get_shot_binding_revision(
        self, owner_id: str, project_id: str, shot_id: str, revision_id: str
    ) -> ShotBindingRevision:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        sa.select(shot_binding_revisions).where(
                            shot_binding_revisions.c.id == revision_id,
                            shot_binding_revisions.c.owner_id == owner_id,
                            shot_binding_revisions.c.project_id == project_id,
                            shot_binding_revisions.c.shot_id == shot_id,
                        )
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise ShotBindingRevisionNotFoundError(revision_id)
        bindings = await self._shot_bindings_for((revision_id,))
        return _row_to_shot_binding_revision(row, bindings.get(revision_id, ()))

    async def next_starting_frame_revision(
        self, owner_id: str, project_id: str, shot_id: str
    ) -> int:
        async with self._engine.connect() as connection:
            value = await connection.scalar(
                sa.select(
                    sa.func.coalesce(sa.func.max(starting_frame_compositions.c.revision), 0) + 1
                ).where(
                    starting_frame_compositions.c.owner_id == owner_id,
                    starting_frame_compositions.c.project_id == project_id,
                    starting_frame_compositions.c.shot_id == shot_id,
                )
            )
        if not isinstance(value, int):
            raise RuntimeError("database did not return a starting-frame revision")
        return value

    @staticmethod
    def _layer_values(
        composition_id: str, position: int, layer: StartingFrameLayer
    ) -> dict[str, object]:
        crop = layer.transform.crop
        mask = layer.mask
        return {
            "composition_id": composition_id,
            "position": position,
            "role": layer.role.value,
            "source_asset_id": layer.source.asset_id,
            "source_asset_version": layer.source.asset_version,
            "source_asset_sha256": layer.source.asset_sha256,
            "source_scope": layer.source.scope.value,
            "source_library_entity_id": layer.source.library_entity_id,
            "source_library_version_id": layer.source.library_version_id,
            "source_library_version_fingerprint": layer.source.library_version_fingerprint,
            "mask_asset_id": mask.asset_id if mask is not None else None,
            "mask_asset_version": mask.asset_version if mask is not None else None,
            "mask_asset_sha256": mask.asset_sha256 if mask is not None else None,
            "mask_scope": mask.scope.value if mask is not None else None,
            "mask_library_entity_id": mask.library_entity_id if mask is not None else None,
            "mask_library_version_id": mask.library_version_id if mask is not None else None,
            "mask_library_version_fingerprint": (
                mask.library_version_fingerprint if mask is not None else None
            ),
            "target_x": layer.transform.x,
            "target_y": layer.transform.y,
            "target_width": layer.transform.width,
            "target_height": layer.transform.height,
            "rotation_millidegrees": layer.transform.rotation_millidegrees,
            "opacity_basis_points": layer.transform.opacity_basis_points,
            "fit": layer.transform.fit.value,
            "crop_x": crop.x if crop is not None else None,
            "crop_y": crop.y if crop is not None else None,
            "crop_width": crop.width if crop is not None else None,
            "crop_height": crop.height if crop is not None else None,
        }

    async def create_starting_frame_composition(
        self, composition: StartingFrameComposition
    ) -> StartingFrameComposition:
        try:
            async with self._engine.begin() as connection:
                row = (
                    (
                        await connection.execute(
                            starting_frame_compositions.insert()
                            .values(
                                id=composition.id,
                                project_id=composition.project_id,
                                owner_id=composition.owner_id,
                                shot_id=composition.shot_id,
                                shot_version=composition.shot_version,
                                shot_binding_revision_id=composition.shot_binding_revision_id,
                                revision=composition.revision,
                                mode=composition.mode.value,
                                status=composition.status.value,
                                canvas_width=composition.canvas_width,
                                canvas_height=composition.canvas_height,
                                background_rgba=composition.background_rgba,
                                output_rights=composition.output_rights.value,
                                framing_notes=composition.framing_notes,
                                pose_notes=composition.pose_notes,
                                action_notes=composition.action_notes,
                                lighting_notes=composition.lighting_notes,
                                visible_speaker_entity_id=composition.visible_speaker_entity_id,
                                fingerprint=composition.fingerprint,
                                created_at=composition.created_at,
                            )
                            .returning(starting_frame_compositions)
                        )
                    )
                    .mappings()
                    .one()
                )
                await connection.execute(
                    starting_frame_layers.insert(),
                    [
                        self._layer_values(composition.id, position, layer)
                        for position, layer in enumerate(composition.layers)
                    ],
                )
        except IntegrityError as error:
            raise LibraryRevisionConflictError(
                "the starting-frame revision was created concurrently; refresh and retry"
            ) from error
        return _row_to_starting_frame(row, composition.layers)

    async def _starting_frame_layers_for(
        self, composition_ids: tuple[str, ...]
    ) -> dict[str, tuple[StartingFrameLayer, ...]]:
        if not composition_ids:
            return {}
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        sa.select(starting_frame_layers)
                        .where(starting_frame_layers.c.composition_id.in_(composition_ids))
                        .order_by(
                            starting_frame_layers.c.composition_id,
                            starting_frame_layers.c.position,
                        )
                    )
                )
                .mappings()
                .all()
            )
        grouped: dict[str, list[StartingFrameLayer]] = {}
        for row in rows:
            grouped.setdefault(row["composition_id"], []).append(_row_to_starting_frame_layer(row))
        return {key: tuple(value) for key, value in grouped.items()}

    async def get_starting_frame_composition(
        self, owner_id: str, project_id: str, shot_id: str, composition_id: str
    ) -> StartingFrameComposition:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        sa.select(starting_frame_compositions).where(
                            starting_frame_compositions.c.id == composition_id,
                            starting_frame_compositions.c.owner_id == owner_id,
                            starting_frame_compositions.c.project_id == project_id,
                            starting_frame_compositions.c.shot_id == shot_id,
                        )
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise StartingFrameCompositionNotFoundError(composition_id)
        layers = await self._starting_frame_layers_for((composition_id,))
        return _row_to_starting_frame(row, layers.get(composition_id, ()))

    async def list_starting_frame_compositions(
        self, owner_id: str, project_id: str, shot_id: str, *, limit: int
    ) -> tuple[StartingFrameComposition, ...]:
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        sa.select(starting_frame_compositions)
                        .where(
                            starting_frame_compositions.c.owner_id == owner_id,
                            starting_frame_compositions.c.project_id == project_id,
                            starting_frame_compositions.c.shot_id == shot_id,
                        )
                        .order_by(starting_frame_compositions.c.revision.desc())
                        .limit(limit)
                    )
                )
                .mappings()
                .all()
            )
        ids = tuple(row["id"] for row in rows)
        layers = await self._starting_frame_layers_for(ids)
        return tuple(_row_to_starting_frame(row, layers.get(row["id"], ())) for row in rows)

    async def publish_starting_frame_render(
        self, composition: StartingFrameComposition, asset: MediaAsset
    ) -> StartingFrameComposition:
        try:
            async with self._engine.begin() as connection:
                await connection.execute(
                    media_assets.insert().values(
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
                        metadata=None,
                        inspector_revision=None,
                        inspected_at=None,
                    )
                )
                row = (
                    (
                        await connection.execute(
                            starting_frame_compositions.update()
                            .where(
                                starting_frame_compositions.c.id == composition.id,
                                starting_frame_compositions.c.owner_id == composition.owner_id,
                                starting_frame_compositions.c.project_id == composition.project_id,
                                starting_frame_compositions.c.shot_id == composition.shot_id,
                                starting_frame_compositions.c.status
                                == StartingFrameStatus.DRAFT.value,
                                starting_frame_compositions.c.fingerprint
                                == composition.fingerprint,
                            )
                            .values(
                                status=composition.status.value,
                                rendered_asset_id=composition.rendered_asset_id,
                                rendered_asset_version=composition.rendered_asset_version,
                                rendered_sha256=composition.rendered_sha256,
                                renderer_revision=composition.renderer_revision,
                                rendered_at=composition.rendered_at,
                            )
                            .returning(starting_frame_compositions)
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    raise LibraryRevisionConflictError(
                        "starting-frame composition is no longer renderable"
                    )
        except IntegrityError as error:
            raise LibraryRevisionConflictError(
                "starting-frame render could not be published"
            ) from error
        return _row_to_starting_frame(row, composition.layers)

    async def approve_starting_frame_composition(
        self, composition: StartingFrameComposition
    ) -> StartingFrameComposition:
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        starting_frame_compositions.update()
                        .where(
                            starting_frame_compositions.c.id == composition.id,
                            starting_frame_compositions.c.owner_id == composition.owner_id,
                            starting_frame_compositions.c.project_id == composition.project_id,
                            starting_frame_compositions.c.shot_id == composition.shot_id,
                            starting_frame_compositions.c.status
                            == StartingFrameStatus.RENDERED.value,
                            starting_frame_compositions.c.rendered_sha256
                            == composition.rendered_sha256,
                        )
                        .values(
                            status=composition.status.value,
                            approved_at=composition.approved_at,
                        )
                        .returning(starting_frame_compositions)
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise LibraryRevisionConflictError("starting-frame composition is no longer approvable")
        return _row_to_starting_frame(row, composition.layers)

    async def next_reference_guidance_revision(
        self, owner_id: str, project_id: str, shot_id: str
    ) -> int:
        async with self._engine.connect() as connection:
            value = await connection.scalar(
                sa.select(
                    sa.func.coalesce(sa.func.max(reference_video_guidance.c.revision), 0) + 1
                ).where(
                    reference_video_guidance.c.owner_id == owner_id,
                    reference_video_guidance.c.project_id == project_id,
                    reference_video_guidance.c.shot_id == shot_id,
                )
            )
        if not isinstance(value, int):
            raise RuntimeError("database did not return a reference-guidance revision")
        return value

    async def create_reference_video_guidance(
        self, guidance: ReferenceVideoGuidance
    ) -> ReferenceVideoGuidance:
        source = guidance.source
        try:
            async with self._engine.begin() as connection:
                row = (
                    (
                        await connection.execute(
                            reference_video_guidance.insert()
                            .values(
                                id=guidance.id,
                                project_id=guidance.project_id,
                                owner_id=guidance.owner_id,
                                shot_id=guidance.shot_id,
                                shot_version=guidance.shot_version,
                                shot_binding_revision_id=guidance.shot_binding_revision_id,
                                revision=guidance.revision,
                                purpose=guidance.purpose.value,
                                status=guidance.status.value,
                                source_asset_id=source.asset_id,
                                source_asset_version=source.asset_version,
                                source_asset_sha256=source.asset_sha256,
                                source_media_type=source.media_type,
                                source_scope=source.scope.value,
                                source_inspector_revision=source.inspector_revision,
                                source_duration_ms=source.duration_ms,
                                source_width=source.width,
                                source_height=source.height,
                                source_frame_rate_numerator=source.frame_rate_numerator,
                                source_frame_rate_denominator=source.frame_rate_denominator,
                                source_library_entity_id=source.library_entity_id,
                                source_library_version_id=source.library_version_id,
                                source_library_version_fingerprint=(
                                    source.library_version_fingerprint
                                ),
                                trim_start_ms=guidance.trim_start_ms,
                                trim_end_ms=guidance.trim_end_ms,
                                guidance_notes=guidance.guidance_notes,
                                fingerprint=guidance.fingerprint,
                                created_at=guidance.created_at,
                            )
                            .returning(reference_video_guidance)
                        )
                    )
                    .mappings()
                    .one()
                )
        except IntegrityError as error:
            raise LibraryRevisionConflictError(
                "the reference-guidance revision was created concurrently; refresh and retry"
            ) from error
        return _row_to_reference_video_guidance(row)

    async def get_reference_video_guidance(
        self, owner_id: str, project_id: str, shot_id: str, guidance_id: str
    ) -> ReferenceVideoGuidance:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        sa.select(reference_video_guidance).where(
                            reference_video_guidance.c.id == guidance_id,
                            reference_video_guidance.c.owner_id == owner_id,
                            reference_video_guidance.c.project_id == project_id,
                            reference_video_guidance.c.shot_id == shot_id,
                        )
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise ReferenceVideoGuidanceNotFoundError(guidance_id)
        return _row_to_reference_video_guidance(row)

    async def list_reference_video_guidance(
        self, owner_id: str, project_id: str, shot_id: str, *, limit: int
    ) -> tuple[ReferenceVideoGuidance, ...]:
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        sa.select(reference_video_guidance)
                        .where(
                            reference_video_guidance.c.owner_id == owner_id,
                            reference_video_guidance.c.project_id == project_id,
                            reference_video_guidance.c.shot_id == shot_id,
                        )
                        .order_by(reference_video_guidance.c.revision.desc())
                        .limit(limit)
                    )
                )
                .mappings()
                .all()
            )
        return tuple(_row_to_reference_video_guidance(row) for row in rows)

    async def approve_reference_video_guidance(
        self, guidance: ReferenceVideoGuidance
    ) -> ReferenceVideoGuidance:
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        reference_video_guidance.update()
                        .where(
                            reference_video_guidance.c.id == guidance.id,
                            reference_video_guidance.c.owner_id == guidance.owner_id,
                            reference_video_guidance.c.project_id == guidance.project_id,
                            reference_video_guidance.c.shot_id == guidance.shot_id,
                            reference_video_guidance.c.status
                            == ReferenceGuidanceStatus.DRAFT.value,
                            reference_video_guidance.c.fingerprint == guidance.fingerprint,
                        )
                        .values(
                            status=guidance.status.value,
                            approved_at=guidance.approved_at,
                        )
                        .returning(reference_video_guidance)
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise LibraryRevisionConflictError("reference guidance is no longer approvable")
        return _row_to_reference_video_guidance(row)

    async def affected_shot_ids(
        self,
        owner_id: str,
        project_id: str,
        entity_id: str,
        version_id: str,
    ) -> tuple[str, ...]:
        latest = (
            sa.select(
                shot_binding_revisions.c.shot_id.label("shot_id"),
                sa.func.max(shot_binding_revisions.c.revision).label("revision"),
            )
            .where(
                shot_binding_revisions.c.owner_id == owner_id,
                shot_binding_revisions.c.project_id == project_id,
            )
            .group_by(shot_binding_revisions.c.shot_id)
            .subquery()
        )
        query = (
            sa.select(shot_binding_revisions.c.shot_id)
            .join(
                latest,
                sa.and_(
                    latest.c.shot_id == shot_binding_revisions.c.shot_id,
                    latest.c.revision == shot_binding_revisions.c.revision,
                ),
            )
            .join(
                shot_library_bindings,
                shot_library_bindings.c.binding_revision_id == shot_binding_revisions.c.id,
            )
            .where(
                shot_library_bindings.c.entity_id == entity_id,
                shot_library_bindings.c.library_version_id == version_id,
            )
            .order_by(shot_binding_revisions.c.shot_id)
        )
        async with self._engine.connect() as connection:
            values = (await connection.scalars(query)).all()
        return tuple(values)
