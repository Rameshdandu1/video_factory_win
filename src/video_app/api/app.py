"""Thin FastAPI adapter for Generation Contract v1."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated

from fastapi import FastAPI, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse

from video_app.api.asset_models import MediaAssetListModel, MediaAssetModel
from video_app.api.film_models import (
    FilmApprovalModel,
    FilmApprovalRequestModel,
    FilmReadinessModel,
    FilmSceneModel,
    FilmSceneSaveModel,
    FilmShotModel,
    FilmShotSaveModel,
    FilmWorkspaceModel,
)
from video_app.api.image_models import (
    ControlledGenerationDraftModel,
    ControlledGenerationProviderListModel,
    ControlledGenerationProviderModel,
    ImageGenerationDraftModel,
    ImageGenerationJobModel,
    ImageGenerationProviderModel,
)
from video_app.api.library_models import (
    AffectedShotListModel,
    FilmBibleNameResolutionModel,
    FilmBibleSnapshotDraftModel,
    FilmBibleSnapshotListModel,
    FilmBibleSnapshotModel,
    LibraryEntityDraftModel,
    LibraryEntityListModel,
    LibraryEntityModel,
    LibraryEntityUpdateModel,
    LibraryVersionDraftModel,
    LibraryVersionListModel,
    LibraryVersionModel,
    ReferenceVideoGuidanceDraftModel,
    ReferenceVideoGuidanceListModel,
    ReferenceVideoGuidanceModel,
    ShotBindingRevisionDraftModel,
    ShotBindingRevisionListModel,
    ShotBindingRevisionModel,
    StartingFrameCompositionListModel,
    StartingFrameCompositionModel,
    StartingFrameDraftModel,
)
from video_app.api.models import (
    ApiErrorModel,
    GenerationRequestModel,
    HealthModel,
    JobModel,
    JobPageModel,
    ModelCapabilityModel,
    ModelListModel,
)
from video_app.api.project_models import (
    ProjectDraftModel,
    ProjectListModel,
    ProjectModel,
    ProjectUpdateModel,
)
from video_app.api.rough_cut_models import (
    RoughCutJobModel,
    RoughCutProviderModel,
    RoughCutSubmitModel,
)
from video_app.api.timeline_models import (
    TimelineApprovalModel,
    TimelineDraftModel,
    TimelineRevisionListModel,
    TimelineRevisionModel,
)
from video_app.api.timeline_render_models import (
    TimelineRenderJobModel,
    TimelineRenderProviderModel,
    TimelineRenderSubmitModel,
)
from video_app.application.assets import (
    AssetNotFoundError,
    AssetTooLargeError,
    InspectLibraryAsset,
    InspectProjectAsset,
    InvalidAssetError,
    ListLibraryAssets,
    ListProjectAssets,
    MediaInspectionError,
    MediaInspectionUnavailableError,
    UploadLibraryAsset,
    UploadProjectAsset,
)
from video_app.application.controlled_generation import (
    ConstraintConflictError,
    ControlledGenerationProvider,
    ControlledGenerationUnavailableError,
    SubmitControlledGeneration,
)
from video_app.application.films import (
    ApproveFilmSubject,
    FilmSubjectNotFoundError,
    GetFilmReadiness,
    GetFilmWorkspace,
    SaveFilmScene,
    SaveFilmShot,
)
from video_app.application.image_generation import (
    CancelImageGeneration,
    GetImageGeneration,
    GetImageGenerationOutput,
    ImageGenerationNotFoundError,
    ImageGenerationProvider,
    ImageGenerationUnavailableError,
    SubmitImageGeneration,
)
from video_app.application.library import (
    ApproveFilmBibleSnapshot,
    ApproveLibraryVersion,
    ApproveReferenceVideoGuidance,
    ApproveStartingFrameComposition,
    CreateFilmBibleSnapshot,
    CreateLibraryEntity,
    CreateLibraryVersion,
    CreateReferenceVideoGuidance,
    CreateShotBindingRevision,
    CreateStartingFrameComposition,
    FilmBibleSnapshotNotFoundError,
    GetLibraryEntity,
    GetReferenceVideoPreview,
    GetStartingFramePreview,
    LibraryEntityNotFoundError,
    LibraryRevisionConflictError,
    LibraryVersionNotFoundError,
    ListAffectedShots,
    ListFilmBibleSnapshots,
    ListLibraryEntities,
    ListLibraryVersions,
    ListReferenceVideoGuidance,
    ListShotBindingRevisions,
    ListStartingFrameCompositions,
    ReferenceVideoGuidanceNotFoundError,
    RenderStartingFrameComposition,
    ResolveFilmBibleName,
    StartingFrameCompositionNotFoundError,
    StartingFrameRenderError,
    UpdateLibraryEntity,
)
from video_app.application.ports import (
    CorrelationIdentifierFactory,
    IdempotencyConflictError,
    JobNotFoundError,
    QueueFullError,
)
from video_app.application.projects import (
    CreateProject,
    GetProject,
    ListProjects,
    ProjectNotFoundError,
    ProjectRevisionConflictError,
    UpdateProject,
)
from video_app.application.rough_cuts import (
    CancelRoughCut,
    GetRoughCut,
    GetRoughCutOutput,
    RoughCutNotFoundError,
    RoughCutProvider,
    RoughCutUnavailableError,
    SubmitRoughCut,
)
from video_app.application.timeline_renders import (
    CancelTimelineRender,
    GetTimelineRender,
    GetTimelineRenderOutput,
    SubmitTimelineRender,
    TimelineRenderNotFoundError,
    TimelineRenderProvider,
    TimelineRenderUnavailableError,
)
from video_app.application.timelines import (
    ApproveTimelineRevision,
    CreateTimelineRevision,
    ListTimelineRevisions,
    TimelineNotFoundError,
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
from video_app.domain.assets import AssetKind, RightsDeclaration
from video_app.domain.jobs import JobStatus
from video_app.domain.library import LibraryEntityKind
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
    create_project: CreateProject | None = None
    get_project: GetProject | None = None
    list_projects: ListProjects | None = None
    update_project: UpdateProject | None = None
    upload_project_asset: UploadProjectAsset | None = None
    list_project_assets: ListProjectAssets | None = None
    inspect_project_asset: InspectProjectAsset | None = None
    create_timeline_revision: CreateTimelineRevision | None = None
    list_timeline_revisions: ListTimelineRevisions | None = None
    approve_timeline_revision: ApproveTimelineRevision | None = None
    save_film_scene: SaveFilmScene | None = None
    save_film_shot: SaveFilmShot | None = None
    get_film_workspace: GetFilmWorkspace | None = None
    get_film_readiness: GetFilmReadiness | None = None
    approve_film_subject: ApproveFilmSubject | None = None
    upload_library_asset: UploadLibraryAsset | None = None
    list_library_assets: ListLibraryAssets | None = None
    inspect_library_asset: InspectLibraryAsset | None = None
    create_library_entity: CreateLibraryEntity | None = None
    get_library_entity: GetLibraryEntity | None = None
    list_library_entities: ListLibraryEntities | None = None
    update_library_entity: UpdateLibraryEntity | None = None
    create_library_version: CreateLibraryVersion | None = None
    list_library_versions: ListLibraryVersions | None = None
    approve_library_version: ApproveLibraryVersion | None = None
    create_film_bible_snapshot: CreateFilmBibleSnapshot | None = None
    list_film_bible_snapshots: ListFilmBibleSnapshots | None = None
    approve_film_bible_snapshot: ApproveFilmBibleSnapshot | None = None
    resolve_film_bible_name: ResolveFilmBibleName | None = None
    create_shot_binding_revision: CreateShotBindingRevision | None = None
    list_shot_binding_revisions: ListShotBindingRevisions | None = None
    list_affected_shots: ListAffectedShots | None = None
    create_starting_frame_composition: CreateStartingFrameComposition | None = None
    list_starting_frame_compositions: ListStartingFrameCompositions | None = None
    render_starting_frame_composition: RenderStartingFrameComposition | None = None
    approve_starting_frame_composition: ApproveStartingFrameComposition | None = None
    get_starting_frame_preview: GetStartingFramePreview | None = None
    create_reference_video_guidance: CreateReferenceVideoGuidance | None = None
    list_reference_video_guidance: ListReferenceVideoGuidance | None = None
    approve_reference_video_guidance: ApproveReferenceVideoGuidance | None = None
    get_reference_video_preview: GetReferenceVideoPreview | None = None
    image_generation_provider: ImageGenerationProvider | None = None
    submit_image_generation: SubmitImageGeneration | None = None
    get_image_generation: GetImageGeneration | None = None
    cancel_image_generation: CancelImageGeneration | None = None
    get_image_generation_output: GetImageGenerationOutput | None = None
    controlled_generation_providers: tuple[ControlledGenerationProvider, ...] = ()
    submit_controlled_generation: SubmitControlledGeneration | None = None
    rough_cut_provider: RoughCutProvider | None = None
    submit_rough_cut: SubmitRoughCut | None = None
    get_rough_cut: GetRoughCut | None = None
    cancel_rough_cut: CancelRoughCut | None = None
    get_rough_cut_output: GetRoughCutOutput | None = None
    timeline_render_provider: TimelineRenderProvider | None = None
    submit_timeline_render: SubmitTimelineRender | None = None
    get_timeline_render: GetTimelineRender | None = None
    cancel_timeline_render: CancelTimelineRender | None = None
    get_timeline_render_output: GetTimelineRenderOutput | None = None


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

    @app.exception_handler(ProjectNotFoundError)
    async def project_not_found_handler(
        _request: Request, _error: ProjectNotFoundError
    ) -> JSONResponse:
        return _error_response(
            services,
            status_code=status.HTTP_404_NOT_FOUND,
            code=ErrorCode.PROJECT_NOT_FOUND,
            message="The requested project was not found.",
            retryable=False,
        )

    @app.exception_handler(ProjectRevisionConflictError)
    async def project_revision_conflict_handler(
        _request: Request, _error: ProjectRevisionConflictError
    ) -> JSONResponse:
        return _error_response(
            services,
            status_code=status.HTTP_409_CONFLICT,
            code=ErrorCode.REVISION_CONFLICT,
            message="The project changed. Refresh it before saving again.",
            retryable=False,
        )

    @app.exception_handler(InvalidAssetError)
    async def invalid_asset_handler(_request: Request, _error: InvalidAssetError) -> JSONResponse:
        return _error_response(
            services,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code=ErrorCode.ASSET_INVALID,
            message="The uploaded file is not an allowed media asset.",
            retryable=False,
        )

    @app.exception_handler(AssetTooLargeError)
    async def asset_too_large_handler(
        _request: Request, _error: AssetTooLargeError
    ) -> JSONResponse:
        return _error_response(
            services,
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            code=ErrorCode.ASSET_TOO_LARGE,
            message="The uploaded file exceeds the configured size limit.",
            retryable=False,
        )

    @app.exception_handler(AssetNotFoundError)
    async def asset_not_found_handler(
        _request: Request, _error: AssetNotFoundError
    ) -> JSONResponse:
        return _error_response(
            services,
            status_code=status.HTTP_404_NOT_FOUND,
            code=ErrorCode.ASSET_NOT_FOUND,
            message="The requested asset was not found.",
            retryable=False,
        )

    @app.exception_handler(MediaInspectionUnavailableError)
    async def inspection_unavailable_handler(
        _request: Request, _error: MediaInspectionUnavailableError
    ) -> JSONResponse:
        return _error_response(
            services,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code=ErrorCode.MEDIA_INSPECTION_UNAVAILABLE,
            message="Verified media inspection is not configured.",
            retryable=False,
        )

    @app.exception_handler(MediaInspectionError)
    async def inspection_failed_handler(
        _request: Request, _error: MediaInspectionError
    ) -> JSONResponse:
        return _error_response(
            services,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code=ErrorCode.MEDIA_INSPECTION_FAILED,
            message="The media could not be inspected safely.",
            retryable=False,
        )

    @app.exception_handler(TimelineNotFoundError)
    async def timeline_not_found_handler(
        _request: Request, _error: TimelineNotFoundError
    ) -> JSONResponse:
        return _error_response(
            services,
            status_code=status.HTTP_404_NOT_FOUND,
            code=ErrorCode.TIMELINE_NOT_FOUND,
            message="The requested timeline revision was not found.",
            retryable=False,
        )

    @app.exception_handler(FilmSubjectNotFoundError)
    async def film_subject_not_found_handler(
        _request: Request, _error: FilmSubjectNotFoundError
    ) -> JSONResponse:
        return _error_response(
            services,
            status_code=status.HTTP_404_NOT_FOUND,
            code=ErrorCode.FILM_SUBJECT_NOT_FOUND,
            message="The requested film scene or shot was not found.",
            retryable=False,
        )

    @app.exception_handler(LibraryEntityNotFoundError)
    async def library_entity_not_found_handler(
        _request: Request, _error: LibraryEntityNotFoundError
    ) -> JSONResponse:
        return _error_response(
            services,
            status_code=status.HTTP_404_NOT_FOUND,
            code=ErrorCode.LIBRARY_ENTITY_NOT_FOUND,
            message="The requested library entity was not found.",
            retryable=False,
        )

    @app.exception_handler(LibraryVersionNotFoundError)
    async def library_version_not_found_handler(
        _request: Request, _error: LibraryVersionNotFoundError
    ) -> JSONResponse:
        return _error_response(
            services,
            status_code=status.HTTP_404_NOT_FOUND,
            code=ErrorCode.LIBRARY_VERSION_NOT_FOUND,
            message="The requested library version was not found.",
            retryable=False,
        )

    @app.exception_handler(LibraryRevisionConflictError)
    async def library_revision_conflict_handler(
        _request: Request, _error: LibraryRevisionConflictError
    ) -> JSONResponse:
        return _error_response(
            services,
            status_code=status.HTTP_409_CONFLICT,
            code=ErrorCode.LIBRARY_REVISION_CONFLICT,
            message="The library item changed. Refresh it before saving again.",
            retryable=False,
        )

    @app.exception_handler(FilmBibleSnapshotNotFoundError)
    async def film_bible_not_found_handler(
        _request: Request, _error: FilmBibleSnapshotNotFoundError
    ) -> JSONResponse:
        return _error_response(
            services,
            status_code=status.HTTP_404_NOT_FOUND,
            code=ErrorCode.FILM_BIBLE_NOT_FOUND,
            message="The requested Film Bible snapshot was not found.",
            retryable=False,
        )

    @app.exception_handler(StartingFrameCompositionNotFoundError)
    async def starting_frame_not_found_handler(
        _request: Request, _error: StartingFrameCompositionNotFoundError
    ) -> JSONResponse:
        return _error_response(
            services,
            status_code=status.HTTP_404_NOT_FOUND,
            code=ErrorCode.STARTING_FRAME_NOT_FOUND,
            message="The requested starting-frame composition was not found.",
            retryable=False,
        )

    @app.exception_handler(StartingFrameRenderError)
    async def starting_frame_render_handler(
        _request: Request, _error: StartingFrameRenderError
    ) -> JSONResponse:
        return _error_response(
            services,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code=ErrorCode.STARTING_FRAME_RENDER_FAILED,
            message="The starting frame could not be rendered from its pinned sources.",
            retryable=False,
        )

    @app.exception_handler(ReferenceVideoGuidanceNotFoundError)
    async def reference_guidance_not_found_handler(
        _request: Request, _error: ReferenceVideoGuidanceNotFoundError
    ) -> JSONResponse:
        return _error_response(
            services,
            status_code=status.HTTP_404_NOT_FOUND,
            code=ErrorCode.REFERENCE_GUIDANCE_NOT_FOUND,
            message="The requested reference-video guidance was not found.",
            retryable=False,
        )

    @app.exception_handler(ImageGenerationUnavailableError)
    async def image_generation_unavailable_handler(
        _request: Request, _error: ImageGenerationUnavailableError
    ) -> JSONResponse:
        return _error_response(
            services,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code=ErrorCode.IMAGE_GENERATION_UNAVAILABLE,
            message="A qualified image-generation runtime is not available.",
            retryable=False,
        )

    @app.exception_handler(RoughCutUnavailableError)
    async def rough_cut_unavailable_handler(
        _request: Request, _error: RoughCutUnavailableError
    ) -> JSONResponse:
        return _error_response(
            services,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code=ErrorCode.MEDIA_RENDER_UNAVAILABLE,
            message="A qualified rough-cut renderer is not configured.",
            retryable=False,
        )

    @app.exception_handler(RoughCutNotFoundError)
    async def rough_cut_not_found_handler(
        _request: Request, _error: RoughCutNotFoundError
    ) -> JSONResponse:
        return _error_response(
            services,
            status_code=status.HTTP_404_NOT_FOUND,
            code=ErrorCode.ROUGH_CUT_NOT_FOUND,
            message="The requested rough-cut job was not found.",
            retryable=False,
        )

    @app.exception_handler(TimelineRenderUnavailableError)
    async def timeline_render_unavailable_handler(
        _request: Request, _error: TimelineRenderUnavailableError
    ) -> JSONResponse:
        return _error_response(
            services,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code=ErrorCode.MEDIA_RENDER_UNAVAILABLE,
            message="A qualified final-timeline renderer is not configured.",
            retryable=False,
        )

    @app.exception_handler(TimelineRenderNotFoundError)
    async def timeline_render_not_found_handler(
        _request: Request, _error: TimelineRenderNotFoundError
    ) -> JSONResponse:
        return _error_response(
            services,
            status_code=status.HTTP_404_NOT_FOUND,
            code=ErrorCode.TIMELINE_RENDER_NOT_FOUND,
            message="The requested timeline-render job was not found.",
            retryable=False,
        )

    @app.exception_handler(ControlledGenerationUnavailableError)
    async def controlled_generation_unavailable_handler(
        _request: Request, _error: ControlledGenerationUnavailableError
    ) -> JSONResponse:
        return _error_response(
            services,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code=ErrorCode.IMAGE_GENERATION_UNAVAILABLE,
            message="The selected controlled-video runtime is not qualified on this deployment.",
            retryable=False,
        )

    @app.exception_handler(ConstraintConflictError)
    async def constraint_conflict_handler(
        _request: Request, _error: ConstraintConflictError
    ) -> JSONResponse:
        return _error_response(
            services,
            status_code=status.HTTP_409_CONFLICT,
            code=ErrorCode.CONSTRAINT_CONFLICT,
            message="The selected provider cannot honor every approved shot constraint.",
            retryable=False,
        )

    @app.exception_handler(ImageGenerationNotFoundError)
    async def image_generation_not_found_handler(
        _request: Request, error: ImageGenerationNotFoundError
    ) -> JSONResponse:
        return _error_response(
            services,
            status_code=status.HTTP_404_NOT_FOUND,
            code=ErrorCode.IMAGE_GENERATION_NOT_FOUND,
            message="The requested image-generation job was not found.",
            retryable=False,
            job_id=str(error.args[0]) if error.args else None,
        )

    @app.exception_handler(IdempotencyConflictError)
    async def idempotency_conflict_handler(
        _request: Request, _error: IdempotencyConflictError
    ) -> JSONResponse:
        return _error_response(
            services,
            status_code=status.HTTP_409_CONFLICT,
            code=ErrorCode.IDEMPOTENCY_CONFLICT,
            message="The idempotency key is already bound to different generation inputs.",
            retryable=False,
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

    if services.upload_library_asset is not None and services.list_library_assets is not None:
        upload_library_asset = services.upload_library_asset
        list_library_assets = services.list_library_assets

        @app.post(
            "/api/v2/library/assets",
            response_model=MediaAssetModel,
            status_code=status.HTTP_201_CREATED,
        )
        async def upload_library_asset_route(
            request: Request,
            filename: Annotated[str, Query(min_length=1, max_length=255)],
            kind: AssetKind,
            rights: RightsDeclaration,
        ) -> MediaAssetModel:
            media_type = request.headers.get("content-type", "").split(";", 1)[0].strip()
            asset = await upload_library_asset(
                kind=kind,
                rights=rights,
                filename=filename,
                media_type=media_type,
                chunks=request.stream(),
            )
            return MediaAssetModel.from_domain(asset)

        @app.get("/api/v2/library/assets", response_model=MediaAssetListModel)
        async def list_library_assets_route(
            limit: Annotated[int, Query(ge=1, le=100)] = 100,
        ) -> MediaAssetListModel:
            assets = await list_library_assets(limit=limit)
            return MediaAssetListModel(
                items=tuple(MediaAssetModel.from_domain(asset) for asset in assets)
            )

        if services.inspect_library_asset is not None:
            inspect_library_asset = services.inspect_library_asset

            @app.post(
                "/api/v2/library/assets/{asset_id}/inspect",
                response_model=MediaAssetModel,
            )
            async def inspect_library_asset_route(asset_id: str) -> MediaAssetModel:
                return MediaAssetModel.from_domain(await inspect_library_asset(asset_id))

    if all(
        service is not None
        for service in (
            services.create_library_entity,
            services.get_library_entity,
            services.list_library_entities,
            services.update_library_entity,
            services.create_library_version,
            services.list_library_versions,
            services.approve_library_version,
        )
    ):
        assert services.create_library_entity is not None
        assert services.get_library_entity is not None
        assert services.list_library_entities is not None
        assert services.update_library_entity is not None
        assert services.create_library_version is not None
        assert services.list_library_versions is not None
        assert services.approve_library_version is not None
        create_library_entity = services.create_library_entity
        get_library_entity = services.get_library_entity
        list_library_entities = services.list_library_entities
        update_library_entity = services.update_library_entity
        create_library_version = services.create_library_version
        list_library_versions = services.list_library_versions
        approve_library_version = services.approve_library_version

        @app.post(
            "/api/v2/library/entities",
            response_model=LibraryEntityModel,
            status_code=status.HTTP_201_CREATED,
        )
        async def create_library_entity_route(
            payload: LibraryEntityDraftModel,
        ) -> LibraryEntityModel:
            entity = await create_library_entity(
                kind=payload.kind,
                display_name=payload.display_name,
                aliases=payload.aliases,
            )
            return LibraryEntityModel.from_domain(entity)

        @app.get("/api/v2/library/entities", response_model=LibraryEntityListModel)
        async def list_library_entities_route(
            kind: LibraryEntityKind | None = None,
            query: Annotated[str | None, Query(max_length=200)] = None,
            limit: Annotated[int, Query(ge=1, le=100)] = 100,
        ) -> LibraryEntityListModel:
            entities = await list_library_entities(kind=kind, query=query, limit=limit)
            return LibraryEntityListModel(
                items=tuple(LibraryEntityModel.from_domain(entity) for entity in entities)
            )

        @app.get("/api/v2/library/entities/{entity_id}", response_model=LibraryEntityModel)
        async def get_library_entity_route(entity_id: str) -> LibraryEntityModel:
            return LibraryEntityModel.from_domain(await get_library_entity(entity_id))

        @app.put("/api/v2/library/entities/{entity_id}", response_model=LibraryEntityModel)
        async def update_library_entity_route(
            entity_id: str, payload: LibraryEntityUpdateModel
        ) -> LibraryEntityModel:
            entity = await update_library_entity(
                entity_id,
                display_name=payload.display_name,
                aliases=payload.aliases,
                expected_version=payload.expected_version,
            )
            return LibraryEntityModel.from_domain(entity)

        @app.post(
            "/api/v2/library/entities/{entity_id}/versions",
            response_model=LibraryVersionModel,
            status_code=status.HTTP_201_CREATED,
        )
        async def create_library_version_route(
            entity_id: str, payload: LibraryVersionDraftModel
        ) -> LibraryVersionModel:
            return LibraryVersionModel.from_domain(
                await create_library_version(entity_id, payload.to_domain())
            )

        @app.get(
            "/api/v2/library/entities/{entity_id}/versions",
            response_model=LibraryVersionListModel,
        )
        async def list_library_versions_route(
            entity_id: str,
            limit: Annotated[int, Query(ge=1, le=100)] = 100,
        ) -> LibraryVersionListModel:
            versions = await list_library_versions(entity_id, limit=limit)
            return LibraryVersionListModel(
                items=tuple(LibraryVersionModel.from_domain(version) for version in versions)
            )

        @app.post(
            "/api/v2/library/entities/{entity_id}/versions/{version_id}/approve",
            response_model=LibraryVersionModel,
        )
        async def approve_library_version_route(
            entity_id: str, version_id: str
        ) -> LibraryVersionModel:
            return LibraryVersionModel.from_domain(
                await approve_library_version(entity_id, version_id)
            )

    if all(
        service is not None
        for service in (
            services.create_project,
            services.get_project,
            services.list_projects,
            services.update_project,
        )
    ):
        assert services.create_project is not None
        assert services.get_project is not None
        assert services.list_projects is not None
        assert services.update_project is not None
        create_project = services.create_project
        get_project = services.get_project
        list_projects = services.list_projects
        update_project = services.update_project

        @app.post(
            "/api/v2/projects",
            response_model=ProjectModel,
            status_code=status.HTTP_201_CREATED,
        )
        async def create_project_route(payload: ProjectDraftModel) -> ProjectModel:
            return ProjectModel.from_domain(await create_project(payload.to_domain()))

        @app.get("/api/v2/projects", response_model=ProjectListModel)
        async def list_projects_route(
            limit: Annotated[int, Query(ge=1, le=100)] = 50,
        ) -> ProjectListModel:
            items = await list_projects(limit=limit)
            return ProjectListModel(items=tuple(ProjectModel.from_domain(item) for item in items))

        @app.get("/api/v2/projects/{project_id}", response_model=ProjectModel)
        async def get_project_route(project_id: str) -> ProjectModel:
            return ProjectModel.from_domain(await get_project(project_id))

        @app.put("/api/v2/projects/{project_id}", response_model=ProjectModel)
        async def update_project_route(
            project_id: str,
            payload: ProjectUpdateModel,
        ) -> ProjectModel:
            return ProjectModel.from_domain(
                await update_project(
                    project_id,
                    payload.to_domain(),
                    expected_version=payload.expected_version,
                )
            )

        if services.upload_project_asset is not None and services.list_project_assets is not None:
            upload_project_asset = services.upload_project_asset
            list_project_assets = services.list_project_assets

            @app.post(
                "/api/v2/projects/{project_id}/assets",
                response_model=MediaAssetModel,
                status_code=status.HTTP_201_CREATED,
            )
            async def upload_project_asset_route(
                project_id: str,
                request: Request,
                filename: Annotated[str, Query(min_length=1, max_length=255)],
                kind: AssetKind,
                rights: RightsDeclaration,
            ) -> MediaAssetModel:
                media_type = request.headers.get("content-type", "").split(";", 1)[0].strip()
                asset = await upload_project_asset(
                    project_id,
                    kind=kind,
                    rights=rights,
                    filename=filename,
                    media_type=media_type,
                    chunks=request.stream(),
                )
                return MediaAssetModel.from_domain(asset)

            @app.get(
                "/api/v2/projects/{project_id}/assets",
                response_model=MediaAssetListModel,
            )
            async def list_project_assets_route(
                project_id: str,
                limit: Annotated[int, Query(ge=1, le=100)] = 100,
            ) -> MediaAssetListModel:
                assets = await list_project_assets(project_id, limit=limit)
                return MediaAssetListModel(
                    items=tuple(MediaAssetModel.from_domain(asset) for asset in assets)
                )

            if services.inspect_project_asset is not None:
                inspect_project_asset = services.inspect_project_asset

                @app.post(
                    "/api/v2/projects/{project_id}/assets/{asset_id}/inspect",
                    response_model=MediaAssetModel,
                )
                async def inspect_project_asset_route(
                    project_id: str, asset_id: str
                ) -> MediaAssetModel:
                    return MediaAssetModel.from_domain(
                        await inspect_project_asset(project_id, asset_id)
                    )

        if (
            services.create_timeline_revision is not None
            and services.list_timeline_revisions is not None
            and services.approve_timeline_revision is not None
        ):
            create_timeline_revision = services.create_timeline_revision
            list_timeline_revisions = services.list_timeline_revisions
            approve_timeline_revision = services.approve_timeline_revision

            @app.post(
                "/api/v2/projects/{project_id}/timelines",
                response_model=TimelineRevisionModel,
                status_code=status.HTTP_201_CREATED,
            )
            async def create_timeline_revision_route(
                project_id: str, payload: TimelineDraftModel
            ) -> TimelineRevisionModel:
                return TimelineRevisionModel.from_domain(
                    await create_timeline_revision(project_id, payload.to_domain())
                )

            @app.get(
                "/api/v2/projects/{project_id}/timelines",
                response_model=TimelineRevisionListModel,
            )
            async def list_timeline_revisions_route(
                project_id: str,
                limit: Annotated[int, Query(ge=1, le=100)] = 50,
            ) -> TimelineRevisionListModel:
                timelines = await list_timeline_revisions(project_id, limit=limit)
                return TimelineRevisionListModel(
                    items=tuple(TimelineRevisionModel.from_domain(item) for item in timelines)
                )

            @app.post(
                "/api/v2/projects/{project_id}/timelines/{timeline_id}/approve",
                response_model=TimelineRevisionModel,
            )
            async def approve_timeline_revision_route(
                project_id: str,
                timeline_id: str,
                payload: TimelineApprovalModel,
            ) -> TimelineRevisionModel:
                return TimelineRevisionModel.from_domain(
                    await approve_timeline_revision(
                        project_id,
                        timeline_id,
                        expected_project_version=payload.expected_project_version,
                    )
                )

        if all(
            service is not None
            for service in (
                services.save_film_scene,
                services.save_film_shot,
                services.get_film_workspace,
                services.get_film_readiness,
                services.approve_film_subject,
            )
        ):
            assert services.save_film_scene is not None
            assert services.save_film_shot is not None
            assert services.get_film_workspace is not None
            assert services.get_film_readiness is not None
            assert services.approve_film_subject is not None
            save_film_scene = services.save_film_scene
            save_film_shot = services.save_film_shot
            get_film_workspace = services.get_film_workspace
            get_film_readiness = services.get_film_readiness
            approve_film_subject = services.approve_film_subject

            @app.get(
                "/api/v2/projects/{project_id}/film",
                response_model=FilmWorkspaceModel,
            )
            async def get_film_workspace_route(project_id: str) -> FilmWorkspaceModel:
                return FilmWorkspaceModel.from_domain(await get_film_workspace(project_id))

            @app.get(
                "/api/v2/projects/{project_id}/film/readiness",
                response_model=FilmReadinessModel,
            )
            async def get_film_readiness_route(project_id: str) -> FilmReadinessModel:
                return FilmReadinessModel.from_domain(await get_film_readiness(project_id))

            @app.post(
                "/api/v2/projects/{project_id}/film/scenes",
                response_model=FilmSceneModel,
                status_code=status.HTTP_201_CREATED,
            )
            async def save_film_scene_route(
                project_id: str, payload: FilmSceneSaveModel
            ) -> FilmSceneModel:
                return FilmSceneModel.from_domain(
                    await save_film_scene(
                        project_id,
                        payload.to_domain(),
                        scene_id=payload.id,
                        expected_version=payload.expected_version,
                    )
                )

            @app.post(
                "/api/v2/projects/{project_id}/film/shots",
                response_model=FilmShotModel,
                status_code=status.HTTP_201_CREATED,
            )
            async def save_film_shot_route(
                project_id: str, payload: FilmShotSaveModel
            ) -> FilmShotModel:
                return FilmShotModel.from_domain(
                    await save_film_shot(
                        project_id,
                        payload.scene_id,
                        payload.to_domain(),
                        shot_id=payload.id,
                        expected_version=payload.expected_version,
                    )
                )

            @app.post(
                "/api/v2/projects/{project_id}/film/approvals",
                response_model=FilmApprovalModel,
                status_code=status.HTTP_201_CREATED,
            )
            async def approve_film_subject_route(
                project_id: str, payload: FilmApprovalRequestModel
            ) -> FilmApprovalModel:
                return FilmApprovalModel.from_domain(
                    await approve_film_subject(
                        project_id,
                        stage=payload.stage,
                        scene_id=payload.scene_id,
                        shot_id=payload.shot_id,
                        evidence_asset_id=payload.evidence_asset_id,
                    )
                )

        if all(
            service is not None
            for service in (
                services.rough_cut_provider,
                services.submit_rough_cut,
                services.get_rough_cut,
                services.cancel_rough_cut,
                services.get_rough_cut_output,
            )
        ):
            assert services.rough_cut_provider is not None
            assert services.submit_rough_cut is not None
            assert services.get_rough_cut is not None
            assert services.cancel_rough_cut is not None
            assert services.get_rough_cut_output is not None
            rough_cut_provider = services.rough_cut_provider
            submit_rough_cut = services.submit_rough_cut
            get_rough_cut = services.get_rough_cut
            cancel_rough_cut = services.cancel_rough_cut
            get_rough_cut_output = services.get_rough_cut_output

            @app.get(
                "/api/v2/projects/{project_id}/film/rough-cuts/provider",
                response_model=RoughCutProviderModel,
            )
            async def get_rough_cut_provider_route(project_id: str) -> RoughCutProviderModel:
                if services.get_project is not None:
                    await services.get_project(project_id)
                return RoughCutProviderModel.from_domain(rough_cut_provider)

            @app.post(
                "/api/v2/projects/{project_id}/film/rough-cuts",
                response_model=RoughCutJobModel,
                status_code=status.HTTP_202_ACCEPTED,
            )
            async def submit_rough_cut_route(
                project_id: str, payload: RoughCutSubmitModel
            ) -> RoughCutJobModel:
                return RoughCutJobModel.from_domain(
                    await submit_rough_cut(
                        project_id,
                        idempotency_key=payload.idempotency_key,
                    )
                )

            @app.get(
                "/api/v2/projects/{project_id}/film/rough-cuts/{job_id}",
                response_model=RoughCutJobModel,
            )
            async def get_rough_cut_route(project_id: str, job_id: str) -> RoughCutJobModel:
                return RoughCutJobModel.from_domain(await get_rough_cut(project_id, job_id))

            @app.post(
                "/api/v2/projects/{project_id}/film/rough-cuts/{job_id}/cancel",
                response_model=RoughCutJobModel,
            )
            async def cancel_rough_cut_route(project_id: str, job_id: str) -> RoughCutJobModel:
                return RoughCutJobModel.from_domain(await cancel_rough_cut(project_id, job_id))

            @app.get(
                "/api/v2/projects/{project_id}/film/rough-cuts/{job_id}/output",
                response_class=FileResponse,
            )
            async def get_rough_cut_output_route(project_id: str, job_id: str) -> FileResponse:
                path = await get_rough_cut_output(project_id, job_id)
                return FileResponse(path, media_type="video/mp4", filename="rough-cut.mp4")

        if all(
            service is not None
            for service in (
                services.timeline_render_provider,
                services.submit_timeline_render,
                services.get_timeline_render,
                services.cancel_timeline_render,
                services.get_timeline_render_output,
            )
        ):
            assert services.timeline_render_provider is not None
            assert services.submit_timeline_render is not None
            assert services.get_timeline_render is not None
            assert services.cancel_timeline_render is not None
            assert services.get_timeline_render_output is not None
            timeline_render_provider = services.timeline_render_provider
            submit_timeline_render = services.submit_timeline_render
            get_timeline_render = services.get_timeline_render
            cancel_timeline_render = services.cancel_timeline_render
            get_timeline_render_output = services.get_timeline_render_output

            @app.get(
                "/api/v2/projects/{project_id}/timeline-renders/provider",
                response_model=TimelineRenderProviderModel,
            )
            async def get_timeline_render_provider_route(
                project_id: str,
            ) -> TimelineRenderProviderModel:
                if services.get_project is not None:
                    await services.get_project(project_id)
                return TimelineRenderProviderModel.from_domain(timeline_render_provider)

            @app.post(
                "/api/v2/projects/{project_id}/timelines/{timeline_id}/renders",
                response_model=TimelineRenderJobModel,
                status_code=status.HTTP_202_ACCEPTED,
            )
            async def submit_timeline_render_route(
                project_id: str,
                timeline_id: str,
                payload: TimelineRenderSubmitModel,
            ) -> TimelineRenderJobModel:
                return TimelineRenderJobModel.from_domain(
                    await submit_timeline_render(
                        project_id,
                        timeline_id,
                        idempotency_key=payload.idempotency_key,
                    )
                )

            @app.get(
                "/api/v2/projects/{project_id}/timelines/{timeline_id}/renders/{job_id}",
                response_model=TimelineRenderJobModel,
            )
            async def get_timeline_render_route(
                project_id: str, timeline_id: str, job_id: str
            ) -> TimelineRenderJobModel:
                return TimelineRenderJobModel.from_domain(
                    await get_timeline_render(project_id, timeline_id, job_id)
                )

            @app.post(
                "/api/v2/projects/{project_id}/timelines/{timeline_id}/renders/{job_id}/cancel",
                response_model=TimelineRenderJobModel,
            )
            async def cancel_timeline_render_route(
                project_id: str, timeline_id: str, job_id: str
            ) -> TimelineRenderJobModel:
                return TimelineRenderJobModel.from_domain(
                    await cancel_timeline_render(project_id, timeline_id, job_id)
                )

            @app.get(
                "/api/v2/projects/{project_id}/timelines/{timeline_id}/renders/{job_id}/output",
                response_class=FileResponse,
            )
            async def get_timeline_render_output_route(
                project_id: str, timeline_id: str, job_id: str
            ) -> FileResponse:
                path = await get_timeline_render_output(project_id, timeline_id, job_id)
                return FileResponse(path, media_type="video/mp4", filename="approved-timeline.mp4")

        if all(
            service is not None
            for service in (
                services.create_film_bible_snapshot,
                services.list_film_bible_snapshots,
                services.approve_film_bible_snapshot,
                services.resolve_film_bible_name,
                services.create_shot_binding_revision,
                services.list_shot_binding_revisions,
                services.list_affected_shots,
            )
        ):
            assert services.create_film_bible_snapshot is not None
            assert services.list_film_bible_snapshots is not None
            assert services.approve_film_bible_snapshot is not None
            assert services.resolve_film_bible_name is not None
            assert services.create_shot_binding_revision is not None
            assert services.list_shot_binding_revisions is not None
            assert services.list_affected_shots is not None
            create_film_bible_snapshot = services.create_film_bible_snapshot
            list_film_bible_snapshots = services.list_film_bible_snapshots
            approve_film_bible_snapshot = services.approve_film_bible_snapshot
            resolve_film_bible_name = services.resolve_film_bible_name
            create_shot_binding_revision = services.create_shot_binding_revision
            list_shot_binding_revisions = services.list_shot_binding_revisions
            list_affected_shots = services.list_affected_shots

            @app.post(
                "/api/v2/projects/{project_id}/film-bible/snapshots",
                response_model=FilmBibleSnapshotModel,
                status_code=status.HTTP_201_CREATED,
            )
            async def create_film_bible_snapshot_route(
                project_id: str, payload: FilmBibleSnapshotDraftModel
            ) -> FilmBibleSnapshotModel:
                snapshot = await create_film_bible_snapshot(
                    project_id, tuple(pin.to_domain() for pin in payload.pins)
                )
                return FilmBibleSnapshotModel.from_domain(snapshot)

            @app.get(
                "/api/v2/projects/{project_id}/film-bible/snapshots",
                response_model=FilmBibleSnapshotListModel,
            )
            async def list_film_bible_snapshots_route(
                project_id: str,
                limit: Annotated[int, Query(ge=1, le=100)] = 100,
            ) -> FilmBibleSnapshotListModel:
                snapshots = await list_film_bible_snapshots(project_id, limit=limit)
                return FilmBibleSnapshotListModel(
                    items=tuple(
                        FilmBibleSnapshotModel.from_domain(snapshot) for snapshot in snapshots
                    )
                )

            @app.post(
                "/api/v2/projects/{project_id}/film-bible/snapshots/{snapshot_id}/approve",
                response_model=FilmBibleSnapshotModel,
            )
            async def approve_film_bible_snapshot_route(
                project_id: str, snapshot_id: str
            ) -> FilmBibleSnapshotModel:
                return FilmBibleSnapshotModel.from_domain(
                    await approve_film_bible_snapshot(project_id, snapshot_id)
                )

            @app.get(
                "/api/v2/projects/{project_id}/film-bible/snapshots/{snapshot_id}/resolve",
                response_model=FilmBibleNameResolutionModel,
            )
            async def resolve_film_bible_name_route(
                project_id: str,
                snapshot_id: str,
                mention: Annotated[str, Query(min_length=1, max_length=200)],
                kind: LibraryEntityKind | None = None,
            ) -> FilmBibleNameResolutionModel:
                return FilmBibleNameResolutionModel.from_domain(
                    await resolve_film_bible_name(project_id, snapshot_id, mention, kind=kind)
                )

            @app.post(
                "/api/v2/projects/{project_id}/film/shots/{shot_id}/bindings",
                response_model=ShotBindingRevisionModel,
                status_code=status.HTTP_201_CREATED,
            )
            async def create_shot_binding_revision_route(
                project_id: str,
                shot_id: str,
                payload: ShotBindingRevisionDraftModel,
            ) -> ShotBindingRevisionModel:
                revision = await create_shot_binding_revision(
                    project_id,
                    shot_id,
                    shot_version=payload.shot_version,
                    snapshot_id=payload.film_bible_snapshot_id,
                    selections=tuple(binding.to_domain() for binding in payload.bindings),
                )
                return ShotBindingRevisionModel.from_domain(revision)

            @app.get(
                "/api/v2/projects/{project_id}/film/shots/{shot_id}/bindings",
                response_model=ShotBindingRevisionListModel,
            )
            async def list_shot_binding_revisions_route(
                project_id: str,
                shot_id: str,
                limit: Annotated[int, Query(ge=1, le=100)] = 100,
            ) -> ShotBindingRevisionListModel:
                revisions = await list_shot_binding_revisions(project_id, shot_id, limit=limit)
                return ShotBindingRevisionListModel(
                    items=tuple(
                        ShotBindingRevisionModel.from_domain(revision) for revision in revisions
                    )
                )

            @app.get(
                "/api/v2/projects/{project_id}/film-bible/affected-shots",
                response_model=AffectedShotListModel,
            )
            async def list_affected_shots_route(
                project_id: str,
                entity_id: Annotated[str, Query(min_length=1)],
                version_id: Annotated[str, Query(min_length=1)],
            ) -> AffectedShotListModel:
                shot_ids = await list_affected_shots(project_id, entity_id, version_id)
                return AffectedShotListModel(
                    entity_id=entity_id,
                    library_version_id=version_id,
                    shot_ids=shot_ids,
                )

        if all(
            service is not None
            for service in (
                services.create_starting_frame_composition,
                services.list_starting_frame_compositions,
                services.render_starting_frame_composition,
                services.approve_starting_frame_composition,
                services.get_starting_frame_preview,
            )
        ):
            assert services.create_starting_frame_composition is not None
            assert services.list_starting_frame_compositions is not None
            assert services.render_starting_frame_composition is not None
            assert services.approve_starting_frame_composition is not None
            assert services.get_starting_frame_preview is not None
            create_starting_frame_composition = services.create_starting_frame_composition
            list_starting_frame_compositions = services.list_starting_frame_compositions
            render_starting_frame_composition = services.render_starting_frame_composition
            approve_starting_frame_composition = services.approve_starting_frame_composition
            get_starting_frame_preview = services.get_starting_frame_preview

            @app.post(
                "/api/v2/projects/{project_id}/film/shots/{shot_id}/starting-frames",
                response_model=StartingFrameCompositionModel,
                status_code=status.HTTP_201_CREATED,
            )
            async def create_starting_frame_composition_route(
                project_id: str,
                shot_id: str,
                payload: StartingFrameDraftModel,
            ) -> StartingFrameCompositionModel:
                return StartingFrameCompositionModel.from_domain(
                    await create_starting_frame_composition(
                        project_id, shot_id, payload.to_domain()
                    )
                )

            @app.get(
                "/api/v2/projects/{project_id}/film/shots/{shot_id}/starting-frames",
                response_model=StartingFrameCompositionListModel,
            )
            async def list_starting_frame_compositions_route(
                project_id: str,
                shot_id: str,
                limit: Annotated[int, Query(ge=1, le=100)] = 100,
            ) -> StartingFrameCompositionListModel:
                values = await list_starting_frame_compositions(project_id, shot_id, limit=limit)
                return StartingFrameCompositionListModel(
                    items=tuple(
                        StartingFrameCompositionModel.from_domain(value) for value in values
                    )
                )

            @app.post(
                "/api/v2/projects/{project_id}/film/shots/{shot_id}/"
                "starting-frames/{composition_id}/render",
                response_model=StartingFrameCompositionModel,
            )
            async def render_starting_frame_composition_route(
                project_id: str, shot_id: str, composition_id: str
            ) -> StartingFrameCompositionModel:
                return StartingFrameCompositionModel.from_domain(
                    await render_starting_frame_composition(project_id, shot_id, composition_id)
                )

            @app.post(
                "/api/v2/projects/{project_id}/film/shots/{shot_id}/"
                "starting-frames/{composition_id}/approve",
                response_model=StartingFrameCompositionModel,
            )
            async def approve_starting_frame_composition_route(
                project_id: str, shot_id: str, composition_id: str
            ) -> StartingFrameCompositionModel:
                return StartingFrameCompositionModel.from_domain(
                    await approve_starting_frame_composition(project_id, shot_id, composition_id)
                )

            @app.get(
                "/api/v2/projects/{project_id}/film/shots/{shot_id}/"
                "starting-frames/{composition_id}/preview",
                response_class=FileResponse,
            )
            async def get_starting_frame_preview_route(
                project_id: str, shot_id: str, composition_id: str
            ) -> FileResponse:
                path = await get_starting_frame_preview(project_id, shot_id, composition_id)
                return FileResponse(path, media_type="image/png", filename="starting-frame.png")

        if all(
            service is not None
            for service in (
                services.create_reference_video_guidance,
                services.list_reference_video_guidance,
                services.approve_reference_video_guidance,
                services.get_reference_video_preview,
            )
        ):
            assert services.create_reference_video_guidance is not None
            assert services.list_reference_video_guidance is not None
            assert services.approve_reference_video_guidance is not None
            assert services.get_reference_video_preview is not None
            create_reference_video_guidance = services.create_reference_video_guidance
            list_reference_video_guidance = services.list_reference_video_guidance
            approve_reference_video_guidance = services.approve_reference_video_guidance
            get_reference_video_preview = services.get_reference_video_preview

            @app.post(
                "/api/v2/projects/{project_id}/film/shots/{shot_id}/reference-guidance",
                response_model=ReferenceVideoGuidanceModel,
                status_code=status.HTTP_201_CREATED,
            )
            async def create_reference_video_guidance_route(
                project_id: str,
                shot_id: str,
                payload: ReferenceVideoGuidanceDraftModel,
            ) -> ReferenceVideoGuidanceModel:
                return ReferenceVideoGuidanceModel.from_domain(
                    await create_reference_video_guidance(project_id, shot_id, payload.to_domain())
                )

            @app.get(
                "/api/v2/projects/{project_id}/film/shots/{shot_id}/reference-guidance",
                response_model=ReferenceVideoGuidanceListModel,
            )
            async def list_reference_video_guidance_route(
                project_id: str,
                shot_id: str,
                limit: Annotated[int, Query(ge=1, le=100)] = 100,
            ) -> ReferenceVideoGuidanceListModel:
                values = await list_reference_video_guidance(project_id, shot_id, limit=limit)
                return ReferenceVideoGuidanceListModel(
                    items=tuple(ReferenceVideoGuidanceModel.from_domain(value) for value in values)
                )

            @app.post(
                "/api/v2/projects/{project_id}/film/shots/{shot_id}/"
                "reference-guidance/{guidance_id}/approve",
                response_model=ReferenceVideoGuidanceModel,
            )
            async def approve_reference_video_guidance_route(
                project_id: str, shot_id: str, guidance_id: str
            ) -> ReferenceVideoGuidanceModel:
                return ReferenceVideoGuidanceModel.from_domain(
                    await approve_reference_video_guidance(project_id, shot_id, guidance_id)
                )

            @app.get(
                "/api/v2/projects/{project_id}/film/shots/{shot_id}/"
                "reference-guidance/{guidance_id}/preview",
                response_class=FileResponse,
            )
            async def get_reference_video_preview_route(
                project_id: str, shot_id: str, guidance_id: str
            ) -> FileResponse:
                preview = await get_reference_video_preview(project_id, shot_id, guidance_id)
                return FileResponse(
                    preview.path,
                    media_type=preview.media_type,
                    filename="reference-video.mp4",
                    content_disposition_type="inline",
                )

    if all(
        service is not None
        for service in (
            services.image_generation_provider,
            services.submit_image_generation,
            services.get_image_generation,
            services.cancel_image_generation,
            services.get_image_generation_output,
        )
    ):
        assert services.image_generation_provider is not None
        assert services.submit_image_generation is not None
        assert services.get_image_generation is not None
        assert services.cancel_image_generation is not None
        assert services.get_image_generation_output is not None
        image_provider = services.image_generation_provider
        submit_image_generation = services.submit_image_generation
        get_image_generation = services.get_image_generation
        cancel_image_generation = services.cancel_image_generation
        get_image_generation_output = services.get_image_generation_output

        @app.get(
            "/api/v2/image-generation/provider",
            response_model=ImageGenerationProviderModel,
        )
        async def get_image_generation_provider_route() -> ImageGenerationProviderModel:
            return ImageGenerationProviderModel.from_domain(image_provider)

        @app.post(
            "/api/v2/projects/{project_id}/film/shots/{shot_id}/"
            "starting-frames/{composition_id}/generations",
            response_model=ImageGenerationJobModel,
            status_code=status.HTTP_202_ACCEPTED,
        )
        async def submit_image_generation_route(
            project_id: str,
            shot_id: str,
            composition_id: str,
            payload: ImageGenerationDraftModel,
        ) -> ImageGenerationJobModel:
            job = await submit_image_generation(
                project_id,
                shot_id,
                composition_id,
                payload.to_domain(),
            )
            return ImageGenerationJobModel.from_domain(job)

        @app.get(
            "/api/v2/projects/{project_id}/film/shots/{shot_id}/generations/{job_id}",
            response_model=ImageGenerationJobModel,
        )
        async def get_image_generation_route(
            project_id: str, shot_id: str, job_id: str
        ) -> ImageGenerationJobModel:
            return ImageGenerationJobModel.from_domain(
                await get_image_generation(project_id, shot_id, job_id)
            )

        @app.post(
            "/api/v2/projects/{project_id}/film/shots/{shot_id}/generations/{job_id}/cancel",
            response_model=ImageGenerationJobModel,
        )
        async def cancel_image_generation_route(
            project_id: str, shot_id: str, job_id: str
        ) -> ImageGenerationJobModel:
            return ImageGenerationJobModel.from_domain(
                await cancel_image_generation(project_id, shot_id, job_id)
            )

        @app.get(
            "/api/v2/projects/{project_id}/film/shots/{shot_id}/generations/{job_id}/output",
            response_class=FileResponse,
        )
        async def get_image_generation_output_route(
            project_id: str, shot_id: str, job_id: str
        ) -> FileResponse:
            output = await get_image_generation_output(project_id, shot_id, job_id)
            return FileResponse(
                output.path,
                media_type=output.metadata.media_type,
                filename=f"{output.job_id}.mp4",
            )

        if services.submit_controlled_generation is not None:
            controlled_providers = services.controlled_generation_providers
            submit_controlled_generation = services.submit_controlled_generation

            @app.get(
                "/api/v2/controlled-generation/providers",
                response_model=ControlledGenerationProviderListModel,
            )
            async def list_controlled_generation_providers_route() -> (
                ControlledGenerationProviderListModel
            ):
                return ControlledGenerationProviderListModel(
                    items=tuple(
                        ControlledGenerationProviderModel.from_domain(provider)
                        for provider in controlled_providers
                    )
                )

            @app.post(
                "/api/v2/projects/{project_id}/film/shots/{shot_id}/"
                "starting-frames/{composition_id}/reference-guidance/{guidance_id}/generations",
                response_model=ImageGenerationJobModel,
                status_code=status.HTTP_202_ACCEPTED,
            )
            async def submit_controlled_generation_route(
                project_id: str,
                shot_id: str,
                composition_id: str,
                guidance_id: str,
                payload: ControlledGenerationDraftModel,
            ) -> ImageGenerationJobModel:
                return ImageGenerationJobModel.from_domain(
                    await submit_controlled_generation(
                        project_id,
                        shot_id,
                        composition_id,
                        guidance_id,
                        payload.to_controlled_domain(),
                    )
                )

    return app
