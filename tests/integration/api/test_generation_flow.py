from __future__ import annotations

import os
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from video_app.api.app import ApiServices, create_app
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
from video_app.domain.models import GenerationMode, ModelCapability, Resolution
from video_app.infrastructure.database import DatabaseSettings, create_database_engine
from video_app.infrastructure.postgres_jobs import PostgresJobRepository
from video_app.infrastructure.runtime import (
    SecureIdentifiers,
    SecureSeedSource,
    StaticCapabilityProvider,
    UtcClock,
)
from video_app.infrastructure.schema import generation_jobs, metadata
from video_app.infrastructure.storage import LocalArtifactStore

DATABASE_URL = os.environ.get("DATABASE_URL")
CAPABILITY = ModelCapability(
    model_id="wan21-t2v",
    display_name="Wan2.1 Text to Video",
    modes=frozenset({GenerationMode.TEXT_TO_VIDEO}),
    resolutions=frozenset({Resolution(832, 480)}),
    frame_counts=frozenset({81}),
)
pytestmark = pytest.mark.integration


async def _noop_close() -> None:
    return None


@unittest.skipUnless(DATABASE_URL, "DATABASE_URL is required for API integration tests")
class GenerationApiFlowTests(unittest.IsolatedAsyncioTestCase):
    engine: AsyncEngine
    client: httpx.AsyncClient
    process_next: ProcessNextJob
    temporary_directory: tempfile.TemporaryDirectory[str]

    async def asyncSetUp(self) -> None:
        assert DATABASE_URL is not None
        self.engine = create_database_engine(DatabaseSettings(DATABASE_URL))
        async with self.engine.begin() as connection:
            await connection.run_sync(metadata.create_all)
            await connection.execute(generation_jobs.delete())

        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name).resolve()
        artifact_root = root / "artifacts"
        backend_root = root / "backend"
        artifact_root.mkdir()
        backend_root.mkdir()

        repository = PostgresJobRepository(
            self.engine,
            queue_capacity=10,
            cursor_secret=b"api-integration-cursor-secret-32-bytes",
        )
        capabilities = StaticCapabilityProvider((CAPABILITY,))
        identifiers = SecureIdentifiers()
        clock = UtcClock()
        artifacts = LocalArtifactStore(artifact_root)
        backend = FakeBackend(backend_root, (CAPABILITY,))
        services = ApiServices(
            submit_job=SubmitJob(
                repository,
                capabilities,
                clock,
                identifiers,
                SecureSeedSource(),
            ),
            get_job=GetJob(repository),
            list_jobs=ListJobs(repository),
            cancel_job=CancelJob(repository, clock),
            get_output=GetJobOutput(repository, artifacts),
            list_models=ListModels(capabilities),
            health_check=HealthCheck(repository),
            identifiers=identifiers,
            close=_noop_close,
        )
        self.process_next = ProcessNextJob(
            repository=repository,
            artifacts=artifacts,
            backend=backend,
            clock=clock,
            identifiers=identifiers,
            worker_id="integration-worker",
            lease_duration=timedelta(seconds=30),
            heartbeat_interval=timedelta(seconds=5),
        )
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(services)),
            base_url="http://test",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        await self.engine.dispose()
        self.temporary_directory.cleanup()

    async def _submit(
        self,
        prompt: str = "  private cinematic prompt  ",
        **overrides: object,
    ) -> httpx.Response:
        payload: dict[str, object] = {
            "mode": "text_to_video",
            "prompt": prompt,
            "model": "wan21-t2v",
            "width": 832,
            "height": 480,
            "frame_count": 81,
        }
        payload.update(overrides)
        return await self.client.post(
            "/api/v1/jobs",
            json=payload,
        )

    async def test_complete_generation_flow_and_safe_output_delivery(self) -> None:
        health = await self.client.get("/api/v1/health")
        models = await self.client.get("/api/v1/models")
        submitted = await self._submit()

        self.assertEqual(health.json(), {"status": "ok"})
        self.assertEqual(models.status_code, 200)
        self.assertEqual(models.json()["items"][0]["id"], "wan21-t2v")
        self.assertEqual(submitted.status_code, 202)
        queued = submitted.json()
        self.assertEqual(queued["status"], "queued")
        self.assertEqual(queued["request"]["prompt"], "private cinematic prompt")
        self.assertIsInstance(queued["request"]["seed"], int)
        job_id = queued["id"]

        missing_output = await self.client.get(f"/api/v1/jobs/{job_id}/output")
        self.assertEqual(missing_output.status_code, 404)
        self.assertEqual(missing_output.json()["code"], "JOB_NOT_FOUND")
        self.assertNotIn(str(Path(self.temporary_directory.name)), missing_output.text)

        processed = await self.process_next()
        self.assertIsNotNone(processed)
        current = await self.client.get(f"/api/v1/jobs/{job_id}")
        output = await self.client.get(f"/api/v1/jobs/{job_id}/output")
        listing = await self.client.get("/api/v1/jobs?limit=1&status=succeeded")

        self.assertEqual(current.json()["status"], "succeeded")
        self.assertEqual(current.json()["result"]["download_url"], f"/api/v1/jobs/{job_id}/output")
        self.assertEqual(output.status_code, 200)
        self.assertEqual(output.headers["content-type"], "video/mp4")
        self.assertEqual(output.content[4:8], b"ftyp")
        self.assertEqual(listing.json()["items"][0]["id"], job_id)

    async def test_cancel_validation_and_not_found_errors_are_safe(self) -> None:
        submitted = await self._submit("cancel me")
        job_id = submitted.json()["id"]
        cancelled = await self.client.post(f"/api/v1/jobs/{job_id}/cancel")
        repeated = await self.client.post(f"/api/v1/jobs/{job_id}/cancel")
        invalid = await self._submit("secret-value-that-must-not-leak" * 200)
        unsupported_model = await self._submit(model="unknown-model")
        unsupported_parameters = await self._submit(width=480)
        unknown = await self.client.get("/api/v1/jobs/not-present")

        self.assertEqual(cancelled.json()["status"], "cancelled")
        self.assertEqual(repeated.json(), cancelled.json())
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(invalid.json()["code"], "INVALID_REQUEST")
        self.assertNotIn("secret-value", invalid.text)
        self.assertEqual(unsupported_model.json()["code"], "UNSUPPORTED_MODEL")
        self.assertEqual(unsupported_parameters.json()["code"], "UNSUPPORTED_PARAMETERS")
        self.assertEqual(unknown.status_code, 404)
        self.assertEqual(unknown.json()["code"], "JOB_NOT_FOUND")
        self.assertNotIn(str(Path(self.temporary_directory.name)), unknown.text)

        accepted = [await self._submit(f"queued prompt {index}") for index in range(10)]
        queue_full = await self._submit("one job too many")
        self.assertTrue(all(response.status_code == 202 for response in accepted))
        self.assertEqual(queue_full.status_code, 429)
        self.assertEqual(queue_full.json()["code"], "QUEUE_FULL")


if __name__ == "__main__":
    unittest.main()
