from __future__ import annotations

from collections.abc import AsyncIterable
from datetime import datetime, timezone
from pathlib import Path

import pytest

from video_app.application.assets import (
    AssetNotFoundError,
    ListLibraryAssets,
    StoredUpload,
    UploadLibraryAsset,
)
from video_app.application.library import (
    ApproveLibraryVersion,
    CreateLibraryEntity,
    CreateLibraryVersion,
    LibraryAssetSelection,
    LibraryEntityNotFoundError,
    LibraryVersionDraft,
    ListLibraryEntities,
)
from video_app.domain.assets import (
    AssetKind,
    AssetScope,
    MediaAsset,
    RightsDeclaration,
)
from video_app.domain.library import (
    LibraryEntity,
    LibraryEntityKind,
    LibraryVersion,
    LibraryVersionKind,
    ReferenceRole,
)

NOW = datetime(2026, 10, 13, tzinfo=timezone.utc)


class Clock:
    def now(self) -> datetime:
        return NOW


class Identifiers:
    def new_asset_id(self) -> str:
        return "asset_library"

    def new_library_entity_id(self) -> str:
        return "library_arjun"

    def new_library_version_id(self) -> str:
        return "library_version_arjun_1"


class Content:
    async def store_upload(
        self,
        *,
        filename: str,
        declared_media_type: str,
        chunks: AsyncIterable[bytes],
        max_bytes: int,
    ) -> StoredUpload:
        payload = b"".join([chunk async for chunk in chunks])
        return StoredUpload(
            storage_key="uploads/" + "1" * 32 + ".png",
            filename=filename,
            media_type="image/png",
            size_bytes=len(payload),
            sha256="a" * 64,
        )

    async def delete(self, storage_key: str) -> None:
        return None

    def resolve_for_read(self, storage_key: str) -> Path:
        return Path("C:/unused")


class Assets:
    def __init__(self) -> None:
        self.items: dict[str, MediaAsset] = {}

    async def create(self, asset: MediaAsset) -> MediaAsset:
        self.items[asset.id] = asset
        return asset

    async def list(self, owner_id: str, project_id: str, *, limit: int) -> tuple[MediaAsset, ...]:
        return tuple(
            asset
            for asset in self.items.values()
            if asset.owner_id == owner_id and asset.project_id == project_id
        )[:limit]

    async def get(self, owner_id: str, project_id: str, asset_id: str) -> MediaAsset:
        asset = await self.get_owner(owner_id, asset_id)
        if asset.project_id != project_id:
            raise AssetNotFoundError(asset_id)
        return asset

    async def list_library(self, owner_id: str, *, limit: int) -> tuple[MediaAsset, ...]:
        return tuple(
            asset
            for asset in self.items.values()
            if asset.owner_id == owner_id and asset.scope is AssetScope.LIBRARY
        )[:limit]

    async def get_owner(self, owner_id: str, asset_id: str) -> MediaAsset:
        asset = self.items.get(asset_id)
        if asset is None or asset.owner_id != owner_id:
            raise AssetNotFoundError(asset_id)
        return asset

    async def update(self, asset: MediaAsset, *, expected_version: int) -> MediaAsset:
        self.items[asset.id] = asset
        return asset


class Library:
    def __init__(self) -> None:
        self.entities: dict[str, LibraryEntity] = {}
        self.versions: dict[str, LibraryVersion] = {}

    async def create_entity(self, entity: LibraryEntity) -> LibraryEntity:
        self.entities[entity.id] = entity
        return entity

    async def get_entity(self, owner_id: str, entity_id: str) -> LibraryEntity:
        entity = self.entities.get(entity_id)
        if entity is None or entity.owner_id != owner_id:
            raise LibraryEntityNotFoundError(entity_id)
        return entity

    async def list_entities(
        self, owner_id: str, *, kind: LibraryEntityKind | None, limit: int
    ) -> tuple[LibraryEntity, ...]:
        return tuple(
            entity
            for entity in self.entities.values()
            if entity.owner_id == owner_id and (kind is None or entity.kind is kind)
        )[:limit]

    async def update_entity(self, entity: LibraryEntity, *, expected_version: int) -> LibraryEntity:
        self.entities[entity.id] = entity
        return entity

    async def next_version_number(self, owner_id: str, entity_id: str) -> int:
        await self.get_entity(owner_id, entity_id)
        return 1 + max(
            (
                version.version_number
                for version in self.versions.values()
                if version.entity_id == entity_id
            ),
            default=0,
        )

    async def create_version(self, version: LibraryVersion) -> LibraryVersion:
        self.versions[version.id] = version
        return version

    async def get_version(self, owner_id: str, entity_id: str, version_id: str) -> LibraryVersion:
        version = self.versions[version_id]
        if version.owner_id != owner_id or version.entity_id != entity_id:
            raise LookupError(version_id)
        return version

    async def list_versions(
        self, owner_id: str, entity_id: str, *, limit: int
    ) -> tuple[LibraryVersion, ...]:
        return tuple(
            version
            for version in self.versions.values()
            if version.owner_id == owner_id and version.entity_id == entity_id
        )[:limit]

    async def approve_version(self, version: LibraryVersion) -> LibraryVersion:
        self.versions[version.id] = version
        return version


async def chunks() -> AsyncIterable[bytes]:
    yield b"\x89PNG\r\n\x1a\nfixture"


@pytest.mark.anyio
async def test_upload_create_and_approve_exact_reusable_version() -> None:
    assets = Assets()
    library = Library()
    identifiers = Identifiers()
    upload = UploadLibraryAsset(assets, Content(), Clock(), identifiers, "owner_a", 1_000_000)
    entity = await CreateLibraryEntity(library, Clock(), identifiers, "owner_a")(
        kind=LibraryEntityKind.CHARACTER,
        display_name="Arjun",
        aliases=("అర్జున్",),
    )

    asset = await upload(
        kind=AssetKind.IMAGE,
        rights=RightsDeclaration.PERMISSIONED,
        filename="arjun.png",
        media_type="image/png",
        chunks=chunks(),
    )
    version = await CreateLibraryVersion(library, assets, Clock(), identifiers, "owner_a")(
        entity.id,
        LibraryVersionDraft(
            kind=LibraryVersionKind.IDENTITY,
            label="Identity pack",
            notes="",
            invariants="Hair and face",
            state_notes="Neutral",
            voice_profile_id=None,
            rights_statement="Permission recorded",
            assets=(LibraryAssetSelection(asset.id, ReferenceRole.IDENTITY_APPEARANCE, "front"),),
        ),
    )

    assert asset.scope is AssetScope.LIBRARY
    assert asset.project_id is None
    assert (await ListLibraryAssets(assets, "owner_a")())[0] == asset
    assert version.bindings[0].asset_id == asset.id
    assert version.bindings[0].asset_sha256 == asset.sha256
    assert version.bindings[0].asset_version == asset.version
    approved = await ApproveLibraryVersion(library, Clock(), "owner_a")(entity.id, version.id)
    assert approved.approved_at == NOW


@pytest.mark.anyio
async def test_owner_boundaries_and_unicode_search_are_enforced() -> None:
    library = Library()
    identifiers = Identifiers()
    await CreateLibraryEntity(library, Clock(), identifiers, "owner_a")(
        kind=LibraryEntityKind.CHARACTER,
        display_name="Arjun",
        aliases=("అర్జున్",),
    )

    assert len(await ListLibraryEntities(library, "owner_a")(query="అర్జు")) == 1
    assert await ListLibraryEntities(library, "owner_b")(query="Arjun") == ()
    with pytest.raises(LibraryEntityNotFoundError):
        await library.get_entity("owner_b", "library_arjun")
