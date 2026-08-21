"""Thin FastAPI adapter for Generation Contract v1."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated

from fastapi import FastAPI, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse

from video_app.api.models import (
    ApiErrorModel,
    GenerationRequestModel,
    HealthModel,
    JobModel,
    JobPageModel,
    ModelCapabilityModel,
    ModelListModel,
)
from video_app.application.ports import (
    CorrelationIdentifierFactory,
    JobNotFoundError,
    QueueFullError,
)
from video_app.application.use_cases import (
    CancelJob,
    GetJob,
    GetJobOutput,
    HealthCheck,
    ListJobs,
    ListModels,
    OutputNotFoundError,
    ServiceUnavailableError,
    SubmitJob,
    UnsupportedModelError,
    UnsupportedParametersError,
)
from video_app.domain.jobs import JobStatus
from video_app.domain.models import DomainValidationError, ErrorCode


@dataclass(frozen=True, slots=True)
class ApiServices:
    submit_job: SubmitJob
    get_job: GetJob
    list_jobs: ListJobs
    cancel_job: CancelJob
    get_output: GetJobOutput
    list_models: ListModels
    health_check: HealthCheck
    identifiers: CorrelationIdentifierFactory
    close: Callable[[], Awaitable[None]]


def _error_response(
    services: ApiServices,
    *,
    status_code: int,
    code: ErrorCode,
    message: str,
    retryable: bool,
    job_id: str | None = None,
    fields: tuple[str, ...] = (),
) -> JSONResponse:
    payload = ApiErrorModel(
        code=code,
        message=message,
        retryable=retryable,
        job_id=job_id,
        correlation_id=services.identifiers.new_correlation_id(),
        fields=fields,
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))


def create_app(services: ApiServices) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await services.close()

    app = FastAPI(title="Video Generation API", version="1.0.0", lifespan=lifespan)

    @app.exception_handler(RequestValidationError)
    async def invalid_request_handler(
        _request: Request, error: RequestValidationError
    ) -> JSONResponse:
        fields = tuple(
            sorted(
                {
                    ".".join(str(part) for part in item["loc"] if part not in {"body", "query"})
                    for item in error.errors()
                }
            )
        )
        return _error_response(
            services,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code=ErrorCode.INVALID_REQUEST,
            message="Request validation failed.",
            retryable=False,
            fields=fields,
        )

    @app.exception_handler(UnsupportedModelError)
    async def unsupported_model_handler(
        _request: Request, _error: UnsupportedModelError
    ) -> JSONResponse:
        return _error_response(
            services,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code=ErrorCode.UNSUPPORTED_MODEL,
            message="The selected model is unavailable.",
            retryable=False,
        )

    @app.exception_handler(UnsupportedParametersError)
    async def unsupported_parameters_handler(
        _request: Request, _error: UnsupportedParametersError
    ) -> JSONResponse:
        return _error_response(
            services,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code=ErrorCode.UNSUPPORTED_PARAMETERS,
            message="The selected generation settings are unsupported.",
            retryable=False,
        )

    @app.exception_handler(DomainValidationError)
    async def domain_validation_handler(
        _request: Request, _error: DomainValidationError
    ) -> JSONResponse:
        return _error_response(
            services,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code=ErrorCode.INVALID_REQUEST,
            message="Request validation failed.",
            retryable=False,
        )

    @app.exception_handler(QueueFullError)
    async def queue_full_handler(_request: Request, _error: QueueFullError) -> JSONResponse:
        return _error_response(
            services,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code=ErrorCode.QUEUE_FULL,
            message="The generation queue is full.",
            retryable=True,
        )

    @app.exception_handler(JobNotFoundError)
    async def job_not_found_handler(_request: Request, error: JobNotFoundError) -> JSONResponse:
        job_id = str(error.args[0]) if error.args else None
        return _error_response(
            services,
            status_code=status.HTTP_404_NOT_FOUND,
            code=ErrorCode.JOB_NOT_FOUND,
            message="The requested job was not found.",
            retryable=False,
            job_id=job_id,
        )

    @app.exception_handler(OutputNotFoundError)
    async def output_not_found_handler(
        _request: Request, error: OutputNotFoundError
    ) -> JSONResponse:
        job_id = str(error.args[0]) if error.args else None
        return _error_response(
            services,
            status_code=status.HTTP_404_NOT_FOUND,
            code=ErrorCode.JOB_NOT_FOUND,
            message="The requested output was not found.",
            retryable=False,
            job_id=job_id,
        )

    @app.exception_handler(ServiceUnavailableError)
    async def unavailable_handler(
        _request: Request, _error: ServiceUnavailableError
    ) -> JSONResponse:
        return _error_response(
            services,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code=ErrorCode.INTERNAL_ERROR,
            message="The application is temporarily unavailable.",
            retryable=True,
        )

    @app.exception_handler(Exception)
    async def internal_error_handler(_request: Request, _error: Exception) -> JSONResponse:
        return _error_response(
            services,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code=ErrorCode.INTERNAL_ERROR,
            message="An unexpected internal error occurred.",
            retryable=True,
        )

    @app.post("/api/v1/jobs", response_model=JobModel, status_code=status.HTTP_202_ACCEPTED)
    async def submit_job(payload: GenerationRequestModel) -> JobModel:
        return JobModel.from_domain(await services.submit_job(payload.to_domain()))

    @app.get("/api/v1/jobs/{job_id}", response_model=JobModel)
    async def get_job(job_id: str) -> JobModel:
        return JobModel.from_domain(await services.get_job(job_id))

    @app.get("/api/v1/jobs", response_model=JobPageModel)
    async def list_jobs(
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        cursor: str | None = None,
        job_status: Annotated[JobStatus | None, Query(alias="status")] = None,
    ) -> JobPageModel:
        page = await services.list_jobs(limit=limit, cursor=cursor, status=job_status)
        return JobPageModel.from_domain(page)

    @app.post("/api/v1/jobs/{job_id}/cancel", response_model=JobModel)
    async def cancel_job(job_id: str) -> JobModel:
        return JobModel.from_domain(await services.cancel_job(job_id))

    @app.get("/api/v1/jobs/{job_id}/output", response_class=FileResponse)
    async def get_output(job_id: str) -> FileResponse:
        output = await services.get_output(job_id)
        return FileResponse(
            output.path,
            media_type=output.metadata.media_type,
            filename="video.mp4",
        )

    @app.get("/api/v1/models", response_model=ModelListModel)
    async def list_models() -> ModelListModel:
        return ModelListModel(
            items=tuple(ModelCapabilityModel.from_domain(item) for item in services.list_models())
        )

    @app.get("/api/v1/health", response_model=HealthModel)
    async def health() -> HealthModel:
        await services.health_check()
        return HealthModel(status="ok")

    return app
