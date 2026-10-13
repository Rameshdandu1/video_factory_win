"""Secure project asset ingestion use cases and ports."""

from __future__ import annotations

from collections.abc import AsyncIterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from video_app.application.ports import Clock
from video_app.application.projects import ProjectRepository
from video_app.domain.assets import (
    AssetKind,
    AssetScope,
    AssetState,
    MediaAsset,
    MediaMetadata,
    RightsDeclaration,
)


class InvalidAssetError(ValueError):
    """Raised when uploaded bytes do not match an allowlisted media type."""


class AssetTooLargeError(ValueError):
    """Raised when an upload exceeds the configured byte limit."""


class AssetNotFoundError(LookupError):
    """Raised when an asset is absent or outside the owner/project boundary."""


class MediaInspectionUnavailableError(RuntimeError):
    """Raised when no verified inspector runtime is configured."""


class MediaInspectionError(RuntimeError):
    """Raised when bounded inspection cannot validate an asset."""


@dataclass(frozen=True, slots=True)
class StoredUpload:
    storage_key: str
    filename: str
    media_type: str
    size_bytes: int
    sha256: str


class AssetIdentifierFactory(Protocol):
    def new_asset_id(self) -> str: ...


class AssetContentStore(Protocol):
    async def store_upload(
        self,
        *,
        filename: str,
        declared_media_type: str,
        chunks: AsyncIterable[bytes],
        max_bytes: int,
    ) -> StoredUpload: ...

    async def delete(self, storage_key: str) -> None: ...

    def resolve_for_read(self, storage_key: str) -> Path: ...


class MediaInspector(Protocol):
    @property
    def revision(self) -> str: ...

    async def inspect(self, path: Path) -> MediaMetadata: ...


class AssetRepository(Protocol):
    async def create(self, asset: MediaAsset) -> MediaAsset: ...

    async def list(
        self, owner_id: str, project_id: str, *, limit: int
    ) -> tuple[MediaAsset, ...]: ...

    async def get(self, owner_id: str, project_id: str, asset_id: str) -> MediaAsset: ...

    async def list_library(self, owner_id: str, *, limit: int) -> tuple[MediaAsset, ...]: ...

    async def get_owner(self, owner_id: str, asset_id: str) -> MediaAsset: ...

    async def update(self, asset: MediaAsset, *, expected_version: int) -> MediaAsset: ...


@dataclass(frozen=True, slots=True)
class UploadProjectAsset:
    projects: ProjectRepository
    assets: AssetRepository
    content: AssetContentStore
    clock: Clock
    identifiers: AssetIdentifierFactory
    owner_id: str
    max_bytes: int

    async def __call__(
        self,
        project_id: str,
        *,
        kind: AssetKind,
        rights: RightsDeclaration,
        filename: str,
        media_type: str,
        chunks: AsyncIterable[bytes],
    ) -> MediaAsset:
        await self.projects.get(self.owner_id, project_id)
        stored = await self.content.store_upload(
            filename=filename,
            declared_media_type=media_type,
            chunks=chunks,
            max_bytes=self.max_bytes,
        )
        if not stored.media_type.startswith(f"{kind.value}/"):
            await self.content.delete(stored.storage_key)
            raise InvalidAssetError("asset kind does not match inspected media")
        asset = MediaAsset(
            id=self.identifiers.new_asset_id(),
            project_id=project_id,
            owner_id=self.owner_id,
            version=1,
            kind=kind,
            state=AssetState.READY,
            original_filename=stored.filename,
            media_type=stored.media_type,
            storage_key=stored.storage_key,
            size_bytes=stored.size_bytes,
            sha256=stored.sha256,
            rights=rights,
            created_at=self.clock.now(),
            scope=AssetScope.PROJECT,
        )
        try:
            return await self.assets.create(asset)
        except BaseException:
            await self.content.delete(stored.storage_key)
            raise


@dataclass(frozen=True, slots=True)
class ListProjectAssets:
    projects: ProjectRepository
    assets: AssetRepository
    owner_id: str

    async def __call__(self, project_id: str, *, limit: int = 100) -> tuple[MediaAsset, ...]:
        if not 1 <= limit <= 100:
            raise ValueError("asset list limit must be between 1 and 100")
        await self.projects.get(self.owner_id, project_id)
        return await self.assets.list(self.owner_id, project_id, limit=limit)


@dataclass(frozen=True, slots=True)
class UploadLibraryAsset:
    """Store one reusable owner-scoped source asset outside any project."""

    assets: AssetRepository
    content: AssetContentStore
    clock: Clock
    identifiers: AssetIdentifierFactory
    owner_id: str
    max_bytes: int

    async def __call__(
        self,
        *,
        kind: AssetKind,
        rights: RightsDeclaration,
        filename: str,
        media_type: str,
        chunks: AsyncIterable[bytes],
    ) -> MediaAsset:
        stored = await self.content.store_upload(
            filename=filename,
            declared_media_type=media_type,
            chunks=chunks,
            max_bytes=self.max_bytes,
        )
        if not stored.media_type.startswith(f"{kind.value}/"):
            await self.content.delete(stored.storage_key)
            raise InvalidAssetError("asset kind does not match inspected media")
        asset = MediaAsset(
            id=self.identifiers.new_asset_id(),
            project_id=None,
            owner_id=self.owner_id,
            version=1,
            kind=kind,
            state=AssetState.READY,
            original_filename=stored.filename,
            media_type=stored.media_type,
            storage_key=stored.storage_key,
            size_bytes=stored.size_bytes,
            sha256=stored.sha256,
            rights=rights,
            created_at=self.clock.now(),
            scope=AssetScope.LIBRARY,
        )
        try:
            return await self.assets.create(asset)
        except BaseException:
            await self.content.delete(stored.storage_key)
            raise


@dataclass(frozen=True, slots=True)
class ListLibraryAssets:
    assets: AssetRepository
    owner_id: str

    async def __call__(self, *, limit: int = 100) -> tuple[MediaAsset, ...]:
        if not 1 <= limit <= 100:
            raise ValueError("asset list limit must be between 1 and 100")
        return await self.assets.list_library(self.owner_id, limit=limit)


@dataclass(frozen=True, slots=True)
class InspectProjectAsset:
    projects: ProjectRepository
    assets: AssetRepository
    content: AssetContentStore
    inspector: MediaInspector | None
    clock: Clock
    owner_id: str

    async def __call__(self, project_id: str, asset_id: str) -> MediaAsset:
        await self.projects.get(self.owner_id, project_id)
        asset = await self.assets.get(self.owner_id, project_id, asset_id)
        if self.inspector is None:
            raise MediaInspectionUnavailableError("verified ffprobe is not configured")
        metadata = await self.inspector.inspect(self.content.resolve_for_read(asset.storage_key))
        revised = asset.with_inspection(
            metadata,
            inspector_revision=self.inspector.revision,
            inspected_at=self.clock.now(),
        )
        return await self.assets.update(revised, expected_version=asset.version)


@dataclass(frozen=True, slots=True)
class InspectLibraryAsset:
    assets: AssetRepository
    content: AssetContentStore
    inspector: MediaInspector | None
    clock: Clock
    owner_id: str

    async def __call__(self, asset_id: str) -> MediaAsset:
        asset = await self.assets.get_owner(self.owner_id, asset_id)
        if asset.scope is not AssetScope.LIBRARY:
            raise AssetNotFoundError(asset_id)
        if self.inspector is None:
            raise MediaInspectionUnavailableError("verified ffprobe is not configured")
        metadata = await self.inspector.inspect(self.content.resolve_for_read(asset.storage_key))
        revised = asset.with_inspection(
            metadata,
            inspector_revision=self.inspector.revision,
            inspected_at=self.clock.now(),
        )
        return await self.assets.update(revised, expected_version=asset.version)
