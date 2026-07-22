import asyncio
from contextlib import asynccontextmanager

from pathlib import Path
import shutil
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .encoder import ClipEncoder
from .index import create_vector_index, filter_relevant_hits
from .jobs import ImportJob, ImportJobRepository, ImportJobService, StagedFile
from .library import (
    SUPPORTED_CONTENT_TYPES,
    ImageLibrary,
    InvalidImageError,
    prepare_image,
)
from .repository import ImageRepository, StoredImage
from .reranker import QwenVLReranker, rerank_candidates
from .schemas import (
    AlbumMembershipRequest,
    AlbumNameRequest,
    AlbumResponse,
    HealthResponse,
    DuplicateGroupResponse,
    DuplicateMemberResponse,
    ImageRecordResponse,
    ImageTagResponse,
    ImportJobResponse,
    ImportResponse,
    SearchHitResponse,
    TagRebuildResponse,
    TagCatalogItemResponse,
    TemporaryGalleryResponse,
    TextSearchRequest,
    UpdateImageTagsRequest,
)
from .tags import DEFAULT_TAGS, ZeroShotTagger
from .sessions import (
    StagedSessionFile,
    TemporaryGalleryCapacityError,
    TemporaryGalleryService,
    TemporaryGallerySnapshot,
)


def seed_demo_library(
    seed_dir: Path,
    image_dir: Path,
    state_dir: Path,
    thumbnail_dir: Path,
) -> None:
    seed_images = seed_dir / "images"
    if seed_images.is_dir() and (not image_dir.exists() or not any(image_dir.iterdir())):
        shutil.copytree(seed_images, image_dir, dirs_exist_ok=True)

    seed_state = seed_dir / "state"
    if seed_state.is_dir() and not (state_dir / "index.sqlite3").exists():
        shutil.copytree(seed_state, state_dir, dirs_exist_ok=True)

    seed_thumbnails = seed_dir / "thumbnails"
    if seed_thumbnails.is_dir() and (
        not thumbnail_dir.exists() or not any(thumbnail_dir.iterdir())
    ):
        shutil.copytree(seed_thumbnails, thumbnail_dir, dirs_exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.mode == "demo" and settings.demo_seed_dir:
        seed_demo_library(
            settings.demo_seed_dir,
            settings.image_dir,
            settings.state_dir,
            settings.thumbnail_dir,
        )
    settings.image_dir.mkdir(parents=True, exist_ok=True)
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    index = create_vector_index(
        settings.index_backend,
        settings.state_dir / "vector-cache-v1.f32",
    )
    encoder = ClipEncoder(settings.clip_model_id)
    tagger = ZeroShotTagger(
        encoder,
        min_score=settings.tag_min_score,
        relative_margin=settings.tag_relative_margin,
        max_tags=settings.tag_max_per_image,
    )
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
        tagger=tagger,
    )
    library.backfill_dimensions()
    library.backfill_visual_fingerprints()
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
    app.state.index_backend = settings.index_backend
    app.state.encoder = encoder
    app.state.reranker = (
        QwenVLReranker(settings.reranker_model_id) if settings.reranker_model_id else None
    )
    app.state.library = library
    app.state.job_repository = job_repository
    app.state.job_service = job_service
    app.state.mode = settings.mode
    app.state.library_writable = settings.mode == "local"
    app.state.temporary_galleries_enabled = settings.mode == "demo"
    app.state.temporary_gallery_service = None
    cleanup_task = None
    stop_cleanup = asyncio.Event()
    if app.state.temporary_galleries_enabled:
        temporary_gallery_service = TemporaryGalleryService(
            settings.temporary_gallery_dir,
            encoder,
            ttl_seconds=settings.temporary_gallery_ttl_seconds,
            max_upload_bytes=settings.temporary_gallery_max_upload_mb * 1024 * 1024,
            max_image_pixels=settings.max_image_pixels,
            thumbnail_max_size=settings.thumbnail_max_size,
            thumbnail_quality=settings.thumbnail_quality,
            max_sessions=settings.temporary_gallery_max_sessions,
            tagger=tagger,
        )
        temporary_gallery_service.initialize()
        app.state.temporary_gallery_service = temporary_gallery_service

        async def cleanup_temporary_galleries() -> None:
            while not stop_cleanup.is_set():
                try:
                    await asyncio.wait_for(stop_cleanup.wait(), timeout=60)
                except TimeoutError:
                    temporary_gallery_service.cleanup_expired()

        cleanup_task = asyncio.create_task(cleanup_temporary_galleries())
    try:
        yield
    finally:
        stop_cleanup.set()
        if cleanup_task:
            await cleanup_task
        if app.state.temporary_gallery_service:
            app.state.temporary_gallery_service.close()
        close_index = getattr(index, "close", None)
        if close_index:
            close_index()


app = FastAPI(
    title="MuseLens API",
    version="0.1.0",
    description="Local-first multimodal image search service.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    reranker = request.app.state.reranker
    return HealthResponse(
        status="ok",
        indexed_images=len(request.app.state.index),
        model_loaded=request.app.state.encoder.loaded,
        reranker_enabled=reranker is not None,
        reranker_loaded=bool(reranker and reranker.loaded),
        index_backend=request.app.state.index_backend,
        mode=request.app.state.mode,
        library_writable=request.app.state.library_writable,
        temporary_galleries_enabled=request.app.state.temporary_galleries_enabled,
        temporary_gallery_max_files=settings.temporary_gallery_max_files,
        temporary_gallery_ttl_seconds=settings.temporary_gallery_ttl_seconds,
        temporary_gallery_max_sessions=settings.temporary_gallery_max_sessions,
    )


def require_library_writes(request: Request) -> None:
    if not request.app.state.library_writable:
        raise HTTPException(
            status_code=403,
            detail="The public demo uses a fixed image library. Import is disabled.",
        )


def temporary_gallery_service(request: Request) -> TemporaryGalleryService:
    service = request.app.state.temporary_gallery_service
    if not request.app.state.temporary_galleries_enabled or service is None:
        raise HTTPException(
            status_code=404, detail="Temporary galleries are only available in demo mode."
        )
    return service


def temporary_gallery_response(snapshot: TemporaryGallerySnapshot) -> TemporaryGalleryResponse:
    return TemporaryGalleryResponse(**vars(snapshot))


def image_record_response(stored) -> ImageRecordResponse:
    return ImageRecordResponse(
        **vars(stored.image),
        width=stored.width,
        height=stored.height,
        size_bytes=stored.size_bytes,
        created_at=stored.created_at,
        tags=[ImageTagResponse(**vars(tag)) for tag in stored.tags],
    )


def duplicate_group_response(group) -> DuplicateGroupResponse:
    return DuplicateGroupResponse(
        group_id=group.group_id,
        potential_savings_bytes=group.potential_savings_bytes,
        members=[
            DuplicateMemberResponse(
                **image_record_response(member.stored).model_dump(),
                distance_to_representative=member.distance_to_representative,
                recommended_keep=member.recommended_keep,
            )
            for member in group.members
        ],
    )


def search_hit_response(stored, score: float | None = None) -> SearchHitResponse:
    return SearchHitResponse(
        **vars(stored.image),
        score=score,
        width=stored.width,
        height=stored.height,
        size_bytes=stored.size_bytes,
        created_at=stored.created_at,
        tags=[ImageTagResponse(**vars(tag)) for tag in stored.tags],
    )


def matches_search_filters(stored, payload: TextSearchRequest) -> bool:
    if payload.content_types and stored.image.content_type not in payload.content_types:
        return False
    if payload.min_width and stored.width < payload.min_width:
        return False
    if payload.max_size_bytes and stored.size_bytes > payload.max_size_bytes:
        return False
    if payload.imported_after and stored.created_at < payload.imported_after:
        return False
    if payload.orientations:
        if stored.width <= 0 or stored.height <= 0:
            return False
        ratio = stored.width / stored.height
        orientation = "landscape" if ratio > 1.08 else "portrait" if ratio < 0.92 else "square"
        if orientation not in payload.orientations:
            return False
    if payload.tags and not set(payload.tags).intersection(tag.slug for tag in stored.tags):
        return False
    return True


@app.post("/v1/tags/rebuild", response_model=TagRebuildResponse)
def rebuild_tags(request: Request) -> TagRebuildResponse:
    require_library_writes(request)
    return TagRebuildResponse(tagged_images=request.app.state.library.rebuild_tags())


@app.get("/v1/tags/catalog", response_model=list[TagCatalogItemResponse])
def tag_catalog() -> list[TagCatalogItemResponse]:
    return [
        TagCatalogItemResponse(
            slug=definition.slug,
            label=definition.label,
            group=definition.group,
        )
        for definition in DEFAULT_TAGS
    ]


def normalized_album_name(name: str) -> str:
    normalized = " ".join(name.split())
    if not normalized:
        raise HTTPException(status_code=400, detail="Album name cannot be blank.")
    return normalized


@app.get("/v1/albums", response_model=list[AlbumResponse])
def list_albums(request: Request) -> list[AlbumResponse]:
    if not request.app.state.library_writable:
        return []
    return [
        AlbumResponse(**vars(album))
        for album in request.app.state.library.repository.list_albums()
    ]


@app.post("/v1/albums", response_model=AlbumResponse, status_code=201)
def create_album(payload: AlbumNameRequest, request: Request) -> AlbumResponse:
    require_library_writes(request)
    album = request.app.state.library.repository.create_album(
        normalized_album_name(payload.name)
    )
    return AlbumResponse(**vars(album))


@app.put("/v1/albums/{album_id}", response_model=AlbumResponse)
def rename_album(
    album_id: str, payload: AlbumNameRequest, request: Request
) -> AlbumResponse:
    require_library_writes(request)
    album = request.app.state.library.repository.rename_album(
        album_id, normalized_album_name(payload.name)
    )
    if album is None:
        raise HTTPException(status_code=404, detail="Album not found.")
    return AlbumResponse(**vars(album))


@app.put("/v1/albums/{album_id}/images", response_model=AlbumResponse)
def update_album_membership(
    album_id: str, payload: AlbumMembershipRequest, request: Request
) -> AlbumResponse:
    require_library_writes(request)
    try:
        album = request.app.state.library.repository.set_album_membership(
            album_id, payload.image_id, payload.present
        )
    except KeyError as error:
        detail = "Album not found." if error.args == ("album",) else "Image not found."
        raise HTTPException(status_code=404, detail=detail) from error
    return AlbumResponse(**vars(album))


@app.delete("/v1/albums/{album_id}", status_code=204)
def delete_album(album_id: str, request: Request) -> Response:
    require_library_writes(request)
    if not request.app.state.library.repository.delete_album(album_id):
        raise HTTPException(status_code=404, detail="Album not found.")
    return Response(status_code=204)


@app.put("/v1/images/{image_id}/tags", response_model=ImageRecordResponse)
def update_image_tags(
    image_id: str,
    payload: UpdateImageTagsRequest,
    request: Request,
) -> ImageRecordResponse:
    require_library_writes(request)
    try:
        stored = request.app.state.library.set_manual_tags(image_id, payload.tags)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Image not found.") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return image_record_response(stored)


@app.post("/v1/images/{image_id}/tags/auto", response_model=ImageRecordResponse)
def restore_image_auto_tags(image_id: str, request: Request) -> ImageRecordResponse:
    require_library_writes(request)
    try:
        stored = request.app.state.library.restore_auto_tags(image_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Image not found.") from error
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return image_record_response(stored)


def sort_filtered_results(results, sort: str):
    if sort == "newest":
        return sorted(results, key=lambda item: item[1].created_at, reverse=True)
    if sort == "oldest":
        return sorted(results, key=lambda item: item[1].created_at)
    if sort == "size_desc":
        return sorted(results, key=lambda item: item[1].size_bytes, reverse=True)
    return results


def indexed_fallback(hit) -> StoredImage:
    """Keep index-only adapters usable while production state remains repository-backed."""
    return StoredImage(
        image=hit.image,
        stored_filename="",
        sha256="",
        size_bytes=0,
        model_id="",
    )


@app.get("/v1/images", response_model=list[ImageRecordResponse])
def list_images(request: Request) -> list[ImageRecordResponse]:
    return [
        image_record_response(stored)
        for stored in request.app.state.library.repository.list_stored()
    ]


@app.get("/v1/duplicates", response_model=list[DuplicateGroupResponse])
def list_duplicate_groups(request: Request) -> list[DuplicateGroupResponse]:
    groups = request.app.state.library.duplicate_groups(
        max_hash_distance=settings.duplicate_hash_distance,
        max_color_distance=settings.duplicate_color_distance,
    )
    return [duplicate_group_response(group) for group in groups]


@app.delete("/v1/images/{image_id}", status_code=204)
def delete_image(image_id: str, request: Request) -> Response:
    require_library_writes(request)
    try:
        request.app.state.library.delete_imported_copy(image_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Image not found.") from error
    return Response(status_code=204)


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
                        raise InvalidImageError(
                            "The selected folder is too large for one import job."
                        )
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


async def stage_temporary_gallery_files(
    files: list[UploadFile],
    session_id: str,
    service: TemporaryGalleryService,
) -> list[StagedSessionFile]:
    staging_dir = service.staging_dir(session_id)
    staging_dir.mkdir(parents=True, exist_ok=False)
    staged: list[StagedSessionFile] = []
    total_bytes = 0
    max_total_bytes = settings.temporary_gallery_max_total_mb * 1024 * 1024
    try:
        for position, upload in enumerate(files):
            content_type = upload.content_type or "application/octet-stream"
            if content_type not in SUPPORTED_CONTENT_TYPES:
                raise InvalidImageError("Only JPEG, PNG and WebP images are supported.")
            suffix = SUPPORTED_CONTENT_TYPES[content_type]
            destination = staging_dir / f"{position:05d}-{uuid4().hex}{suffix}"
            file_bytes = 0
            with destination.open("wb") as output:
                while chunk := await upload.read(1024 * 1024):
                    file_bytes += len(chunk)
                    total_bytes += len(chunk)
                    if file_bytes > service.max_upload_bytes:
                        raise InvalidImageError(
                            f"Each temporary image must be at most "
                            f"{settings.temporary_gallery_max_upload_mb} MB."
                        )
                    if total_bytes > max_total_bytes:
                        raise InvalidImageError(
                            f"A temporary gallery must be at most "
                            f"{settings.temporary_gallery_max_total_mb} MB."
                        )
                    output.write(chunk)
            staged.append(
                StagedSessionFile(
                    filename=upload.filename or "image",
                    content_type=content_type,
                    path=destination,
                )
            )
    except Exception:
        shutil.rmtree(service.root / session_id, ignore_errors=True)
        raise
    return staged


@app.post("/v1/import-jobs", response_model=ImportJobResponse, status_code=202)
async def create_import_job(
    request: Request,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
) -> ImportJobResponse:
    require_library_writes(request)
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
    require_library_writes(request)
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
    require_library_writes(request)
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
        width=result.stored.width,
        height=result.stored.height,
        size_bytes=result.stored.size_bytes,
        created_at=result.stored.created_at,
        tags=[ImageTagResponse(**vars(tag)) for tag in result.stored.tags],
        duplicate=result.duplicate,
        sha256=result.stored.sha256,
    )


@app.post("/v1/images/batch", response_model=list[ImportResponse], status_code=201)
async def index_image_batch(
    request: Request,
    files: list[UploadFile] = File(...),
) -> list[ImportResponse]:
    require_library_writes(request)
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
            width=result.stored.width,
            height=result.stored.height,
            size_bytes=result.stored.size_bytes,
            created_at=result.stored.created_at,
            tags=[ImageTagResponse(**vars(tag)) for tag in result.stored.tags],
            duplicate=result.duplicate,
            sha256=result.stored.sha256,
        )
        for result in results
    ]


@app.post("/v1/search/text", response_model=list[SearchHitResponse])
def search_by_text(payload: TextSearchRequest, request: Request) -> list[SearchHitResponse]:
    index = request.app.state.index
    repository = request.app.state.library.repository
    if len(index) == 0:
        return []
    normalized_query = payload.query.strip()
    if not normalized_query:
        results = [
            (None, stored)
            for stored in repository.list_stored()
            if matches_search_filters(stored, payload)
        ]
        return [
            search_hit_response(stored)
            for _, stored in sort_filtered_results(results, payload.sort)[: payload.top_k]
        ]

    reranker = request.app.state.reranker
    recall_query = (
        settings.reranker_recall_template.format(query=normalized_query)
        if reranker
        else normalized_query
    )
    query_vector = request.app.state.encoder.encode_texts([recall_query])[0]
    candidates = index.search(query_vector, min(len(index), 100))
    filtered = []
    for hit in candidates:
        stored = repository.find_by_id(hit.image.image_id)
        if stored is None and not any(
            [
                payload.content_types,
                payload.orientations,
                payload.tags,
                payload.min_width,
                payload.max_size_bytes,
                payload.imported_after,
            ]
        ):
            stored = indexed_fallback(hit)
        if stored and matches_search_filters(stored, payload):
            filtered.append((hit, stored))
    if reranker:
        filtered = rerank_candidates(
            normalized_query,
            filtered,
            request.app.state.library.original_path,
            reranker,
            settings.reranker_min_score,
            settings.reranker_recall_k,
        )
    else:
        relevant_hits = filter_relevant_hits(
            [hit for hit, _ in filtered],
            absolute_floor=(
                settings.search_min_score if request.app.state.mode == "demo" else None
            ),
            relative_margin=settings.search_relative_margin,
            max_results=payload.top_k,
        )
        relevant_ids = {hit.image.image_id for hit in relevant_hits}
        filtered = [(hit, stored) for hit, stored in filtered if hit.image.image_id in relevant_ids]
    filtered = sort_filtered_results(filtered, payload.sort)[: payload.top_k]
    return [search_hit_response(stored, hit.score) for hit, stored in filtered]


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
    try:
        query_vector = request.app.state.encoder.encode_images([candidate.image])[0]
    finally:
        candidate.image.close()
    hits = request.app.state.index.search(
        query_vector,
        min(len(request.app.state.index), settings.default_top_k),
    )
    exact_match = request.app.state.library.repository.find_by_sha256(candidate.digest)
    if exact_match:
        hits = [hit for hit in hits if hit.image.image_id != exact_match.image.image_id]
    hits = filter_relevant_hits(
        hits,
        absolute_floor=settings.search_min_score if request.app.state.mode == "demo" else None,
        relative_margin=settings.image_search_relative_margin,
        max_results=settings.default_top_k,
    )
    return [
        search_hit_response(stored, hit.score)
        for hit in hits
        if (stored := request.app.state.library.repository.find_by_id(hit.image.image_id))
    ]


@app.post(
    "/v1/demo/sessions/{session_id}/search/image",
    response_model=list[SearchHitResponse],
)
async def search_temporary_gallery_by_image(
    session_id: str,
    request: Request,
    file: UploadFile = File(...),
) -> list[SearchHitResponse]:
    service = temporary_gallery_service(request)
    try:
        gallery = service.gallery(session_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Temporary gallery not found or expired."
        ) from error
    if gallery.status not in {"completed", "partial"}:
        raise HTTPException(status_code=409, detail="Temporary gallery is still being indexed.")

    content = await file.read()
    try:
        candidate = prepare_image(
            filename=file.filename or "query",
            content_type=file.content_type or "application/octet-stream",
            content=content,
            max_upload_bytes=settings.temporary_gallery_max_upload_mb * 1024 * 1024,
            max_image_pixels=settings.max_image_pixels,
        )
    except InvalidImageError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    try:
        query_vector = service.encoder.encode_images([candidate.image])[0]
    finally:
        candidate.image.close()
    hits = gallery.index.search(query_vector, min(len(gallery.index), settings.default_top_k))
    exact_match = gallery.library.repository.find_by_sha256(candidate.digest)
    if exact_match:
        hits = [hit for hit in hits if hit.image.image_id != exact_match.image.image_id]
    hits = filter_relevant_hits(
        hits,
        absolute_floor=None,
        relative_margin=settings.image_search_relative_margin,
        max_results=settings.default_top_k,
    )
    return [
        search_hit_response(stored, hit.score)
        for hit in hits
        if (stored := gallery.library.repository.find_by_id(hit.image.image_id))
    ]


@app.post(
    "/v1/demo/sessions",
    response_model=TemporaryGalleryResponse,
    status_code=202,
)
async def create_temporary_gallery(
    request: Request,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
) -> TemporaryGalleryResponse:
    service = temporary_gallery_service(request)
    if not files:
        raise HTTPException(status_code=400, detail="Select at least one image.")
    if len(files) > settings.temporary_gallery_max_files:
        raise HTTPException(
            status_code=400,
            detail=(
                f"A temporary gallery can contain at most "
                f"{settings.temporary_gallery_max_files} images."
            ),
        )
    session_id = service.new_session_id()
    try:
        staged = await stage_temporary_gallery_files(files, session_id, service)
    except InvalidImageError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    try:
        snapshot = service.create(session_id, staged)
    except TemporaryGalleryCapacityError as error:
        shutil.rmtree(service.root / session_id, ignore_errors=True)
        raise HTTPException(status_code=429, detail=str(error)) from error
    background_tasks.add_task(service.run, session_id)
    return temporary_gallery_response(snapshot)


@app.get(
    "/v1/demo/sessions/{session_id}",
    response_model=TemporaryGalleryResponse,
)
def get_temporary_gallery(session_id: str, request: Request) -> TemporaryGalleryResponse:
    service = temporary_gallery_service(request)
    try:
        return temporary_gallery_response(service.get(session_id))
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Temporary gallery not found or expired."
        ) from error


@app.get(
    "/v1/demo/sessions/{session_id}/images",
    response_model=list[ImageRecordResponse],
)
def list_temporary_gallery_images(
    session_id: str,
    request: Request,
) -> list[ImageRecordResponse]:
    service = temporary_gallery_service(request)
    try:
        gallery = service.gallery(session_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Temporary gallery not found or expired."
        ) from error
    return [image_record_response(stored) for stored in gallery.library.repository.list_stored()]


@app.get(
    "/v1/demo/sessions/{session_id}/duplicates",
    response_model=list[DuplicateGroupResponse],
)
def list_temporary_gallery_duplicate_groups(
    session_id: str,
    request: Request,
) -> list[DuplicateGroupResponse]:
    service = temporary_gallery_service(request)
    try:
        gallery = service.gallery(session_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Temporary gallery not found or expired."
        ) from error
    groups = gallery.library.duplicate_groups(
        max_hash_distance=settings.duplicate_hash_distance,
        max_color_distance=settings.duplicate_color_distance,
    )
    return [duplicate_group_response(group) for group in groups]


@app.get("/v1/demo/sessions/{session_id}/images/{image_id}/content")
def temporary_gallery_image_content(
    session_id: str,
    image_id: str,
    request: Request,
) -> FileResponse:
    service = temporary_gallery_service(request)
    try:
        gallery = service.gallery(session_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Temporary gallery not found or expired."
        ) from error
    stored = gallery.library.repository.find_by_id(image_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Image not found in this temporary gallery.")
    return FileResponse(
        gallery.library.original_path(stored),
        media_type=stored.image.content_type,
        headers={"Cache-Control": "private, no-store"},
    )


@app.get("/v1/demo/sessions/{session_id}/images/{image_id}/thumbnail")
def temporary_gallery_image_thumbnail(
    session_id: str,
    image_id: str,
    request: Request,
) -> FileResponse:
    service = temporary_gallery_service(request)
    try:
        gallery = service.gallery(session_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Temporary gallery not found or expired."
        ) from error
    stored = gallery.library.repository.find_by_id(image_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Image not found in this temporary gallery.")
    return FileResponse(
        gallery.library.ensure_thumbnail(stored),
        media_type="image/webp",
        headers={"Cache-Control": "private, no-store"},
    )


@app.post(
    "/v1/demo/sessions/{session_id}/search/text",
    response_model=list[SearchHitResponse],
)
def search_temporary_gallery_by_text(
    session_id: str,
    payload: TextSearchRequest,
    request: Request,
) -> list[SearchHitResponse]:
    service = temporary_gallery_service(request)
    try:
        gallery = service.gallery(session_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Temporary gallery not found or expired."
        ) from error
    if gallery.status not in {"completed", "partial"}:
        raise HTTPException(status_code=409, detail="Temporary gallery is still being indexed.")
    repository = gallery.library.repository
    normalized_query = payload.query.strip()
    if not normalized_query:
        results = [
            (None, stored)
            for stored in repository.list_stored()
            if matches_search_filters(stored, payload)
        ]
        return [
            search_hit_response(stored)
            for _, stored in sort_filtered_results(results, payload.sort)[: payload.top_k]
        ]

    query_vector = service.encoder.encode_texts([normalized_query])[0]
    candidates = gallery.index.search(query_vector, min(len(gallery.index), 100))
    filtered = []
    for hit in candidates:
        stored = repository.find_by_id(hit.image.image_id)
        if stored and matches_search_filters(stored, payload):
            filtered.append((hit, stored))
    relevant_hits = filter_relevant_hits(
        [hit for hit, _ in filtered],
        absolute_floor=None,
        relative_margin=settings.temporary_gallery_search_relative_margin,
        max_results=payload.top_k,
    )
    relevant_ids = {hit.image.image_id for hit in relevant_hits}
    filtered = [(hit, stored) for hit, stored in filtered if hit.image.image_id in relevant_ids]
    filtered = sort_filtered_results(filtered, payload.sort)[: payload.top_k]
    return [search_hit_response(stored, hit.score) for hit, stored in filtered]


@app.delete("/v1/demo/sessions/{session_id}", status_code=204)
def delete_temporary_gallery(session_id: str, request: Request) -> Response:
    service = temporary_gallery_service(request)
    try:
        deleted = service.delete(session_id)
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if not deleted:
        raise HTTPException(status_code=404, detail="Temporary gallery not found or expired.")
    return Response(status_code=204)


if settings.frontend_dist.is_dir():
    app.mount(
        "/",
        StaticFiles(directory=settings.frontend_dist, html=True),
        name="frontend",
    )
