"""Composition root for API and worker processes."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import uvicorn
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from video_app.api.app import ApiServices, create_app
from video_app.application.recovery import RecoverExpiredLeases
from video_app.application.runner import WorkerRunner
from video_app.application.use_cases import (
    CancelJob,
    GetJob,
    GetJobOutput,
    HealthCheck,
    ListJobs,
    ListModels,
    SubmitJob,
)
from video_app.application.worker import ProcessNextJob
from video_app.backends.fake import FakeBackend
from video_app.infrastructure.database import create_database_engine
from video_app.infrastructure.postgres_jobs import PostgresJobRepository
from video_app.infrastructure.runtime import (
    RuntimeSettings,
    SecureIdentifiers,
    SecureSeedSource,
    StaticCapabilityProvider,
    UtcClock,
)
from video_app.infrastructure.storage import LocalArtifactStore


@dataclass(frozen=True, slots=True)
class RuntimeComponents:
    settings: RuntimeSettings
    engine: AsyncEngine
    repository: PostgresJobRepository
    artifacts: LocalArtifactStore
    temporary_root: Path
    capabilities: StaticCapabilityProvider
    clock: UtcClock
    identifiers: SecureIdentifiers


def build_runtime(settings: RuntimeSettings) -> RuntimeComponents:
    data_root = settings.data_root.resolve()
    artifact_root = data_root / "artifacts"
    temporary_root = data_root / "temporary"
    artifact_root.mkdir(parents=True, exist_ok=True)
    temporary_root.mkdir(parents=True, exist_ok=True)
    engine = create_database_engine(settings.database)
    return RuntimeComponents(
        settings=settings,
        engine=engine,
        repository=PostgresJobRepository(
            engine,
            queue_capacity=settings.queue_capacity,
            cursor_secret=settings.cursor_secret,
        ),
        artifacts=LocalArtifactStore(artifact_root),
        temporary_root=temporary_root,
        capabilities=StaticCapabilityProvider((settings.capability,)),
        clock=UtcClock(),
        identifiers=SecureIdentifiers(),
    )


def create_api_app(settings: RuntimeSettings) -> FastAPI:
    runtime = build_runtime(settings)
    services = ApiServices(
        submit_job=SubmitJob(
            runtime.repository,
            runtime.capabilities,
            runtime.clock,
            runtime.identifiers,
            SecureSeedSource(),
        ),
        get_job=GetJob(runtime.repository),
        list_jobs=ListJobs(runtime.repository),
        cancel_job=CancelJob(runtime.repository, runtime.clock),
        get_output=GetJobOutput(runtime.repository, runtime.artifacts),
        list_models=ListModels(runtime.capabilities),
        health_check=HealthCheck(runtime.repository),
        identifiers=runtime.identifiers,
        close=runtime.engine.dispose,
    )
    return create_app(services)


def create_api_app_from_environment() -> FastAPI:
    return create_api_app(RuntimeSettings.from_environment())


def build_worker(settings: RuntimeSettings) -> tuple[WorkerRunner, AsyncEngine]:
    runtime = build_runtime(settings)
    backend = FakeBackend(runtime.temporary_root, (settings.capability,))
    process_next = ProcessNextJob(
        repository=runtime.repository,
        artifacts=runtime.artifacts,
        backend=backend,
        clock=runtime.clock,
        identifiers=runtime.identifiers,
        worker_id=f"worker_{uuid4().hex}",
        lease_duration=settings.lease_duration,
        heartbeat_interval=settings.heartbeat_interval,
    )
    recovery = RecoverExpiredLeases(
        runtime.repository,
        runtime.clock,
        runtime.identifiers,
    )
    return (
        WorkerRunner(process_next, recovery, settings.poll_interval_seconds),
        runtime.engine,
    )


def _settings_from_file(value: str) -> RuntimeSettings:
    return RuntimeSettings.from_file(Path(value).resolve(strict=True))


def api_main() -> None:
    parser = argparse.ArgumentParser(description="Run the video generation API")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    arguments = parser.parse_args()
    settings = _settings_from_file(arguments.env_file)
    uvicorn.run(create_api_app(settings), host=arguments.host, port=arguments.port)


async def _run_worker(settings: RuntimeSettings, *, once: bool) -> None:
    runner, engine = build_worker(settings)
    try:
        if once:
            await runner.run_once()
        else:
            await runner.run_until_stopped(asyncio.Event())
    finally:
        await engine.dispose()


def worker_main() -> None:
    parser = argparse.ArgumentParser(description="Run the video generation worker")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--once", action="store_true")
    arguments = parser.parse_args()
    try:
        asyncio.run(_run_worker(_settings_from_file(arguments.env_file), once=arguments.once))
    except KeyboardInterrupt:
        return
