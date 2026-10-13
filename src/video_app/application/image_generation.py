"""Approved starting-frame submission through the canonical generation queue."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from video_app.application.assets import AssetRepository
from video_app.application.films import FilmRepository
from video_app.application.library import FilmBibleRepository
from video_app.application.ports import (
    ArtifactReader,
    Clock,
    IdentifierFactory,
    JobNotFoundError,
    JobRepository,
    SeedSource,
)
from video_app.application.projects import ProjectRepository
from video_app.application.use_cases import JobOutput, OutputNotFoundError
from video_app.domain.assets import AssetKind, AssetState
from video_app.domain.jobs import GenerationJob
from video_app.domain.library import StartingFrameStatus
from video_app.domain.models import (
    MAX_SEED,
    MIN_SEED,
    DomainValidationError,
    GenerationMode,
    GenerationRequest,
    ImageConditioning,
    Resolution,
)


class ImageGenerationUnavailableError(RuntimeError):
    """Raised when the qualified I2V provider is not enabled."""


class ImageGenerationNotFoundError(LookupError):
    """Raised when a job is not part of the requested owner/project/shot."""


@dataclass(frozen=True, slots=True)
class ImageGenerationProvider:
    backend_name: str
    backend_revision: str
    model_id: str
    display_name: str
    task: str
    area_preset: Resolution
    frame_count: int
    enabled: bool
    runtime_state: str
    unavailable_reason: str | None

    def __post_init__(self) -> None:
        for value, field in (
            (self.backend_name, "I2V backend name"),
            (self.backend_revision, "I2V backend revision"),
            (self.model_id, "I2V model id"),
            (self.display_name, "I2V display name"),
            (self.task, "I2V task"),
            (self.runtime_state, "I2V runtime state"),
        ):
            if not value or value.isspace():
                raise ValueError(f"{field} must not be empty")
        if self.frame_count < 1:
            raise ValueError("I2V frame count must be positive")
        if self.enabled and self.unavailable_reason is not None:
            raise ValueError("enabled I2V providers cannot have an unavailable reason")
        if not self.enabled and not self.unavailable_reason:
            raise ValueError("disabled I2V providers require an unavailable reason")


@dataclass(frozen=True, slots=True)
class ImageGenerationDraft:
    prompt: str
    idempotency_key: str
    seed: int | None = None


def normalize_generation_prompt(value: str) -> str:
    normalized = value.strip()
    if not 1 <= len(normalized) <= 2_000:
        raise DomainValidationError("prompt length must be between 1 and 2000")
    return normalized


def validate_generation_idempotency_key(value: str) -> str:
    if not value or value.isspace() or len(value) > 200 or "\x00" in value:
        raise DomainValidationError("idempotency key must contain 1 to 200 safe characters")
    return value


def _require_image_job(
    job: GenerationJob,
    *,
    owner_id: str,
    project_id: str,
    shot_id: str,
) -> None:
    conditioning = job.request.image_conditioning
    if (
        conditioning is None
        or conditioning.owner_id != owner_id
        or conditioning.project_id != project_id
        or conditioning.shot_id != shot_id
    ):
        raise ImageGenerationNotFoundError(job.id)


@dataclass(frozen=True, slots=True)
class SubmitImageGeneration:
    projects: ProjectRepository
    films: FilmRepository
    film_bibles: FilmBibleRepository
    assets: AssetRepository
    jobs: JobRepository
    provider: ImageGenerationProvider
    clock: Clock
    identifiers: IdentifierFactory
    seeds: SeedSource
    owner_id: str

    async def __call__(
        self,
        project_id: str,
        shot_id: str,
        composition_id: str,
        draft: ImageGenerationDraft,
    ) -> GenerationJob:
        if not self.provider.enabled:
            raise ImageGenerationUnavailableError(self.provider.runtime_state)
        await self.projects.get(self.owner_id, project_id)
        shot = await self.films.get_shot(self.owner_id, project_id, shot_id)
        composition = await self.film_bibles.get_starting_frame_composition(
            self.owner_id, project_id, shot_id, composition_id
        )
        if composition.status is not StartingFrameStatus.APPROVED:
            raise DomainValidationError("image generation requires an approved starting frame")
        if composition.shot_version != shot.version:
            raise DomainValidationError(
                "the approved starting frame belongs to an older shot revision"
            )
        if (
            composition.rendered_asset_id is None
            or composition.rendered_asset_version is None
            or composition.rendered_sha256 is None
        ):
            raise DomainValidationError("approved starting frame metadata is incomplete")
        asset = await self.assets.get(self.owner_id, project_id, composition.rendered_asset_id)
        if asset.kind is not AssetKind.IMAGE or asset.state not in {
            AssetState.READY,
            AssetState.INSPECTED,
        }:
            raise DomainValidationError("starting-frame output must be a ready image")
        if (
            asset.version != composition.rendered_asset_version
            or asset.sha256 != composition.rendered_sha256
        ):
            raise DomainValidationError("starting-frame bytes no longer match their approval pin")

        prompt = normalize_generation_prompt(draft.prompt)
        idempotency_key = validate_generation_idempotency_key(draft.idempotency_key)
        seed = self.seeds.new_seed() if draft.seed is None else draft.seed
        if not MIN_SEED <= seed <= MAX_SEED:
            raise DomainValidationError("seed must be a signed 64-bit integer")
        manifest_payload = {
            "owner_id": self.owner_id,
            "project_id": project_id,
            "shot_id": shot_id,
            "shot_version": shot.version,
            "composition_id": composition.id,
            "composition_revision": composition.revision,
            "composition_fingerprint": composition.fingerprint,
            "source_asset_id": asset.id,
            "source_asset_version": asset.version,
            "source_asset_sha256": asset.sha256,
            "source_width": composition.canvas_width,
            "source_height": composition.canvas_height,
            "backend": self.provider.backend_name,
            "backend_revision": self.provider.backend_revision,
            "model": self.provider.model_id,
            "task": self.provider.task,
            "area_preset": [
                self.provider.area_preset.width,
                self.provider.area_preset.height,
            ],
            "frame_count": self.provider.frame_count,
            "prompt": prompt,
            "seed": seed,
        }
        manifest_fingerprint = hashlib.sha256(
            json.dumps(manifest_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        conditioning = ImageConditioning(
            owner_id=self.owner_id,
            project_id=project_id,
            shot_id=shot_id,
            shot_version=shot.version,
            composition_id=composition.id,
            composition_revision=composition.revision,
            composition_fingerprint=composition.fingerprint,
            source_asset_id=asset.id,
            source_asset_version=asset.version,
            source_asset_sha256=asset.sha256,
            source_storage_key=asset.storage_key,
            source_width=composition.canvas_width,
            source_height=composition.canvas_height,
            required_backend=self.provider.backend_name,
            required_backend_revision=self.provider.backend_revision,
            manifest_fingerprint=manifest_fingerprint,
        )
        request = GenerationRequest(
            prompt=prompt,
            model=self.provider.model_id,
            resolution=self.provider.area_preset,
            frame_count=self.provider.frame_count,
            seed=seed,
            mode=GenerationMode.IMAGE_TO_VIDEO,
            image_conditioning=conditioning,
        )
        job = GenerationJob.queued(
            self.identifiers.new_job_id(),
            request,
            self.clock.now(),
            idempotency_key=idempotency_key,
        )
        return await self.jobs.enqueue(job)


@dataclass(frozen=True, slots=True)
class GetImageGeneration:
    jobs: JobRepository
    owner_id: str

    async def __call__(self, project_id: str, shot_id: str, job_id: str) -> GenerationJob:
        try:
            job = await self.jobs.get(job_id)
        except JobNotFoundError as error:
            raise ImageGenerationNotFoundError(job_id) from error
        _require_image_job(job, owner_id=self.owner_id, project_id=project_id, shot_id=shot_id)
        return job


@dataclass(frozen=True, slots=True)
class CancelImageGeneration:
    jobs: JobRepository
    clock: Clock
    owner_id: str

    async def __call__(self, project_id: str, shot_id: str, job_id: str) -> GenerationJob:
        try:
            job = await self.jobs.get(job_id)
        except JobNotFoundError as error:
            raise ImageGenerationNotFoundError(job_id) from error
        _require_image_job(job, owner_id=self.owner_id, project_id=project_id, shot_id=shot_id)
        return await self.jobs.request_cancellation(job_id, self.clock.now())


@dataclass(frozen=True, slots=True)
class GetImageGenerationOutput:
    jobs: JobRepository
    artifacts: ArtifactReader
    owner_id: str

    async def __call__(self, project_id: str, shot_id: str, job_id: str) -> JobOutput:
        try:
            job = await self.jobs.get(job_id)
        except JobNotFoundError as error:
            raise ImageGenerationNotFoundError(job_id) from error
        _require_image_job(job, owner_id=self.owner_id, project_id=project_id, shot_id=shot_id)
        if job.result is None:
            raise OutputNotFoundError(job_id)
        try:
            path: Path = self.artifacts.resolve_for_read(job.result.storage_key)
        except (FileNotFoundError, ValueError) as error:
            raise OutputNotFoundError(job_id) from error
        return JobOutput(job.id, job.result, path)
