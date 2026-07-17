from contextlib import asynccontextmanager

from pathlib import Path
import shutil
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .config import settings
from .encoder import ClipEncoder
from .index import VectorIndex, filter_relevant_hits
from .jobs import ImportJob, ImportJobRepository, ImportJobService, StagedFile
from .library import (
    SUPPORTED_CONTENT_TYPES,
    ImageLibrary,
    InvalidImageError,
    prepare_image,
)
from .repository import ImageRepository
from .schemas import (
    HealthResponse,
    ImageRecordResponse,
    ImportJobResponse,
    ImportResponse,
    SearchHitResponse,
    TextSearchRequest,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.image_dir.mkdir(parents=True, exist_ok=True)
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    index = VectorIndex()
    encoder = ClipEncoder(settings.clip_model_id)
    repository = ImageRepository(settings.state_dir / "index.sqlite3")
    repository.initialize()
    library = ImageLibrary(
        settings.image_dir,
        repository,
        index,
        encoder,
        thumbnail_dir=settings.thumbnail_dir,
        thumbnail_max_size=settings.thumbnail_max_size,
        thumbnail_quality=settings.thumbnail_quality,
    )
    library.restore_index()
    job_repository = ImportJobRepository(settings.state_dir / "index.sqlite3")
    job_repository.initialize()
    job_repository.recover_interrupted_jobs()
    job_service = ImportJobService(
        settings.state_dir / "import-jobs",
        job_repository,
        library,
        max_upload_bytes=settings.max_upload_mb * 1024 * 1024,
        max_image_pixels=settings.max_image_pixels,
    )
    app.state.index = index
    app.state.encoder = encoder
    app.state.library = library
    app.state.job_repository = job_repository
    app.state.job_service = job_service
    yield


app = FastAPI(
    title="MuseLens API",
    version="0.1.0",
    description="Local-first multimodal image search service.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    return HealthResponse(
        status="ok",
        indexed_images=len(request.app.state.index),
        model_loaded=request.app.state.encoder.loaded,
    )


@app.get("/v1/images", response_model=list[ImageRecordResponse])
def list_images(request: Request) -> list[ImageRecordResponse]:
    return [ImageRecordResponse(**vars(image)) for image in request.app.state.index.list_images()]


@app.get("/v1/images/{image_id}/content")
def image_content(image_id: str, request: Request) -> FileResponse:
    stored = request.app.state.library.repository.find_by_id(image_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Image not found.")
    path = request.app.state.library.original_path(stored)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Stored image file is missing.")
    return FileResponse(path, media_type=stored.image.content_type)


@app.get("/v1/images/{image_id}/thumbnail")
def image_thumbnail(image_id: str, request: Request) -> FileResponse:
    stored = request.app.state.library.repository.find_by_id(image_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Image not found.")
    try:
        path = request.app.state.library.ensure_thumbnail(stored)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="Stored image file is missing.") from error
    except InvalidImageError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    return FileResponse(
        path,
        media_type="image/webp",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


def job_response(job: ImportJob) -> ImportJobResponse:
    return ImportJobResponse(**vars(job))


async def stage_job_files(
    files: list[UploadFile],
    job_id: str,
    staging_root: Path,
) -> list[StagedFile]:
    job_dir = staging_root / job_id
    job_dir.mkdir(parents=True, exist_ok=False)
    staged: list[StagedFile] = []
    total_bytes = 0
    max_file_bytes = settings.max_upload_mb * 1024 * 1024
    max_total_bytes = settings.max_job_total_mb * 1024 * 1024
    try:
        for position, upload in enumerate(files):
            content_type = upload.content_type or "application/octet-stream"
            if content_type not in SUPPORTED_CONTENT_TYPES:
                raise InvalidImageError("Only JPEG, PNG and WebP images are supported.")
            suffix = SUPPORTED_CONTENT_TYPES[content_type]
            staged_filename = f"{position:05d}-{uuid4().hex}{suffix}"
            destination = job_dir / staged_filename
            file_bytes = 0
            with destination.open("wb") as output:
                while chunk := await upload.read(1024 * 1024):
                    file_bytes += len(chunk)
                    total_bytes += len(chunk)
                    if file_bytes > max_file_bytes:
                        raise InvalidImageError("Uploaded image is too large.")
                    if total_bytes > max_total_bytes:
                        raise InvalidImageError("The selected folder is too large for one import job.")
                    output.write(chunk)
            staged.append(
                StagedFile(
                    file_id=uuid4().hex,
                    filename=upload.filename or "image",
                    content_type=content_type,
                    staged_filename=staged_filename,
                )
            )
    except Exception:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    return staged


@app.post("/v1/import-jobs", response_model=ImportJobResponse, status_code=202)
async def create_import_job(
    request: Request,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
) -> ImportJobResponse:
    if not files:
        raise HTTPException(status_code=400, detail="Select at least one image.")
    if len(files) > settings.max_job_files:
        raise HTTPException(
            status_code=400,
            detail=f"An import job can contain at most {settings.max_job_files} files.",
        )
    service: ImportJobService = request.app.state.job_service
    job_id = service.new_job_id()
    try:
        staged = await stage_job_files(files, job_id, service.staging_dir)
    except InvalidImageError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    job = request.app.state.job_repository.create(job_id, staged)
    background_tasks.add_task(service.run, job_id)
    return job_response(job)


@app.get("/v1/import-jobs/latest", response_model=ImportJobResponse | None)
def get_latest_import_job(request: Request) -> ImportJobResponse | None:
    job = request.app.state.job_repository.latest()
    return job_response(job) if job else None


@app.get("/v1/import-jobs/{job_id}", response_model=ImportJobResponse)
def get_import_job(job_id: str, request: Request) -> ImportJobResponse:
    job = request.app.state.job_repository.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Import job not found.")
    return job_response(job)


@app.post("/v1/import-jobs/{job_id}/retry", response_model=ImportJobResponse, status_code=202)
def retry_import_job(
    job_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
) -> ImportJobResponse:
    try:
        job = request.app.state.job_repository.reset_failed(job_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Import job not found.") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    background_tasks.add_task(request.app.state.job_service.run, job_id)
    return job_response(job)


@app.post("/v1/images", response_model=ImportResponse, status_code=201)
async def index_image(
    request: Request,
    file: UploadFile = File(...),
) -> ImportResponse:
    content = await file.read()
    try:
        candidate = prepare_image(
            filename=file.filename or "image",
            content_type=file.content_type or "application/octet-stream",
            content=content,
            max_upload_bytes=settings.max_upload_mb * 1024 * 1024,
            max_image_pixels=settings.max_image_pixels,
        )
    except InvalidImageError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    result = request.app.state.library.import_candidates([candidate])[0]
    return ImportResponse(
        **vars(result.stored.image),
        duplicate=result.duplicate,
        sha256=result.stored.sha256,
    )


@app.post("/v1/images/batch", response_model=list[ImportResponse], status_code=201)
async def index_image_batch(
    request: Request,
    files: list[UploadFile] = File(...),
) -> list[ImportResponse]:
    if len(files) > settings.max_batch_files:
        raise HTTPException(
            status_code=400,
            detail=f"A batch can contain at most {settings.max_batch_files} files.",
        )
    candidates = []
    try:
        for file in files:
            candidates.append(
                prepare_image(
                    filename=file.filename or "image",
                    content_type=file.content_type or "application/octet-stream",
                    content=await file.read(),
                    max_upload_bytes=settings.max_upload_mb * 1024 * 1024,
                    max_image_pixels=settings.max_image_pixels,
                )
            )
    except InvalidImageError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    results = request.app.state.library.import_candidates(candidates)
    return [
        ImportResponse(
            **vars(result.stored.image),
            duplicate=result.duplicate,
            sha256=result.stored.sha256,
        )
        for result in results
    ]


@app.post("/v1/search/text", response_model=list[SearchHitResponse])
def search_by_text(payload: TextSearchRequest, request: Request) -> list[SearchHitResponse]:
    if len(request.app.state.index) == 0:
        return []
    query_vector = request.app.state.encoder.encode_texts([payload.query])[0]
    hits = request.app.state.index.search(query_vector, payload.top_k)
    hits = filter_relevant_hits(
        hits,
        absolute_floor=settings.search_min_score,
        relative_margin=settings.search_relative_margin,
        max_results=payload.top_k,
    )
    return [
        SearchHitResponse(
            image_id=hit.image.image_id,
            score=hit.score,
            filename=hit.image.filename,
        )
        for hit in hits
    ]


@app.post("/v1/search/image", response_model=list[SearchHitResponse])
async def search_by_image(
    request: Request,
    file: UploadFile = File(...),
) -> list[SearchHitResponse]:
    if len(request.app.state.index) == 0:
        return []
    content = await file.read()
    try:
        candidate = prepare_image(
            filename=file.filename or "query",
            content_type=file.content_type or "application/octet-stream",
            content=content,
            max_upload_bytes=settings.max_upload_mb * 1024 * 1024,
            max_image_pixels=settings.max_image_pixels,
        )
    except InvalidImageError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    query_vector = request.app.state.encoder.encode_images([candidate.image])[0]
    hits = request.app.state.index.search(query_vector, settings.default_top_k)
    return [
        SearchHitResponse(
            image_id=hit.image.image_id,
            score=hit.score,
            filename=hit.image.filename,
        )
        for hit in hits
    ]
