from __future__ import annotations

from collections.abc import AsyncIterable, AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

import pytest

from video_app.application.assets import (
    AssetNotFoundError,
    InspectLibraryAsset,
    InspectProjectAsset,
    InvalidAssetError,
    ListProjectAssets,
    StoredUpload,
    UploadLibraryAsset,
    UploadProjectAsset,
)
from video_app.application.projects import CreateProject
from video_app.domain.assets import (
    AssetKind,
    AssetScope,
    MediaAsset,
    MediaMetadata,
    RightsDeclaration,
)
from video_app.domain.projects import (
    AspectRatio,
    BudgetPolicy,
    ExportSettings,
    Project,
    ProjectDraft,
    ProjectMode,
    ProviderSelections,
)


class FixedClock:
    def __init__(self, value: datetime | None = None) -> None:
        self.value = value or datetime(2026, 10, 12, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self.value


class MemoryProjects:
    def __init__(self) -> None:
        self.items: dict[str, Project] = {}

    async def create(self, project: Project) -> Project:
        self.items[project.id] = project
        return project

    async def get(self, owner_id: str, project_id: str) -> Project:
        return self.items[project_id]

    async def list(self, owner_id: str, *, limit: int) -> tuple[Project, ...]:
        return tuple(self.items.values())[:limit]

    async def update(self, project: Project, *, expected_version: int) -> Project:
        self.items[project.id] = project
        return project


def _draft() -> ProjectDraft:
    return ProjectDraft(
        "Conversation",
        "en",
        ProjectMode.SHORT,
        30_000,
        AspectRatio.LANDSCAPE,
        ExportSettings(1280, 720, 30),
        ProviderSelections("wan21", "uploaded"),
        BudgetPolicy(),
    )


class Identifiers:
    def new_project_id(self) -> str:
        return "project_fixed"

    def new_asset_id(self) -> str:
        return "asset_fixed"


class MemoryAssets:
    def __init__(self) -> None:
        self.items: list[MediaAsset] = []

    async def create(self, asset: MediaAsset) -> MediaAsset:
        self.items.append(asset)
        return asset

    async def list(self, owner_id: str, project_id: str, *, limit: int) -> tuple[MediaAsset, ...]:
        return tuple(
            item
            for item in self.items
            if item.owner_id == owner_id and item.project_id == project_id
        )[:limit]

    async def get(self, owner_id: str, project_id: str, asset_id: str) -> MediaAsset:
        for item in self.items:
            if item.owner_id == owner_id and item.project_id == project_id and item.id == asset_id:
                return item
        raise AssetNotFoundError(asset_id)

    async def list_library(self, owner_id: str, *, limit: int) -> tuple[MediaAsset, ...]:
        return tuple(
            item
            for item in self.items
            if item.owner_id == owner_id and item.scope is AssetScope.LIBRARY
        )[:limit]

    async def get_owner(self, owner_id: str, asset_id: str) -> MediaAsset:
        for item in self.items:
            if item.owner_id == owner_id and item.id == asset_id:
                return item
        raise AssetNotFoundError(asset_id)

    async def update(self, asset: MediaAsset, *, expected_version: int) -> MediaAsset:
        self.items = [asset if item.id == asset.id else item for item in self.items]
        return asset


class MemoryContent:
    def __init__(self, media_type: str = "audio/wav") -> None:
        self.media_type = media_type
        self.deleted: list[str] = []

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
            "uploads/" + "a" * 32 + ".wav", filename, self.media_type, len(payload), "b" * 64
        )

    async def delete(self, storage_key: str) -> None:
        self.deleted.append(storage_key)

    def resolve_for_read(self, storage_key: str) -> Path:
        return Path("C:/unused")


class Inspector:
    @property
    def revision(self) -> str:
        return "ffprobe pinned"

    async def inspect(self, path: Path) -> MediaMetadata:
        return MediaMetadata("wav", 250, sample_rate=48_000, channels=1, sample_count=12_000)


async def chunks() -> AsyncIterator[bytes]:
    yield b"RIFFxxxxWAVE"


@pytest.mark.anyio
async def test_upload_and_list_asset_are_project_and_owner_scoped() -> None:
    projects = MemoryProjects()
    identifiers = Identifiers()
    clock = FixedClock(datetime(2026, 10, 12, tzinfo=timezone.utc))
    project = await CreateProject(projects, clock, identifiers, "owner_one")(_draft())
    assets = MemoryAssets()
    content = MemoryContent()

    asset = await UploadProjectAsset(
        projects, assets, content, clock, identifiers, "owner_one", 1024
    )(
        project.id,
        kind=AssetKind.AUDIO,
        rights=RightsDeclaration.PERMISSIONED,
        filename="voice.wav",
        media_type="audio/wav",
        chunks=chunks(),
    )

    assert asset.id == "asset_fixed"
    assert asset.rights is RightsDeclaration.PERMISSIONED
    assert await ListProjectAssets(projects, assets, "owner_one")(project.id) == (asset,)


@pytest.mark.anyio
async def test_kind_mismatch_removes_stored_blob() -> None:
    projects = MemoryProjects()
    identifiers = Identifiers()
    clock = FixedClock()
    project = await CreateProject(projects, clock, identifiers, "owner_one")(_draft())
    content = MemoryContent("audio/wav")

    with pytest.raises(InvalidAssetError):
        await UploadProjectAsset(
            projects, MemoryAssets(), content, clock, identifiers, "owner_one", 1024
        )(
            project.id,
            kind=AssetKind.VIDEO,
            rights=RightsDeclaration.OWNED,
            filename="voice.wav",
            media_type="audio/wav",
            chunks=chunks(),
        )

    assert content.deleted == ["uploads/" + "a" * 32 + ".wav"]


@pytest.mark.anyio
async def test_inspection_creates_a_new_measured_asset_version() -> None:
    projects = MemoryProjects()
    identifiers = Identifiers()
    clock = FixedClock()
    project = await CreateProject(projects, clock, identifiers, "owner_one")(_draft())
    assets = MemoryAssets()
    content = MemoryContent()
    uploaded = await UploadProjectAsset(
        projects, assets, content, clock, identifiers, "owner_one", 1024
    )(
        project.id,
        kind=AssetKind.AUDIO,
        rights=RightsDeclaration.PERMISSIONED,
        filename="voice.wav",
        media_type="audio/wav",
        chunks=chunks(),
    )

    inspected = await InspectProjectAsset(
        projects, assets, content, Inspector(), clock, "owner_one"
    )(project.id, uploaded.id)

    assert inspected.version == 2
    assert inspected.metadata is not None
    assert inspected.metadata.sample_count == 12_000


@pytest.mark.anyio
async def test_library_asset_uses_same_verified_inspection_path() -> None:
    assets = MemoryAssets()
    content = MemoryContent()
    clock = FixedClock()
    uploaded = await UploadLibraryAsset(assets, content, clock, Identifiers(), "owner_one", 1024)(
        kind=AssetKind.AUDIO,
        rights=RightsDeclaration.PERMISSIONED,
        filename="voice.wav",
        media_type="audio/wav",
        chunks=chunks(),
    )

    inspected = await InspectLibraryAsset(assets, content, Inspector(), clock, "owner_one")(
        uploaded.id
    )

    assert inspected.scope is AssetScope.LIBRARY
    assert inspected.version == 2
    assert inspected.inspector_revision == "ffprobe pinned"
