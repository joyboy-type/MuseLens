from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    status: str
    indexed_images: int
    model_loaded: bool
    index_backend: Literal["numpy", "faiss"]
    mode: Literal["local", "demo"]
    library_writable: bool
    temporary_galleries_enabled: bool
    temporary_gallery_max_files: int
    temporary_gallery_ttl_seconds: int
    temporary_gallery_max_sessions: int


class ImageRecordResponse(BaseModel):
    image_id: str
    filename: str
    content_type: str
    width: int = 0
    height: int = 0
    size_bytes: int = 0
    created_at: str = ""


class ImportResponse(ImageRecordResponse):
    duplicate: bool
    sha256: str


class TextSearchRequest(BaseModel):
    query: str = Field(default="", max_length=300)
    top_k: int = Field(default=12, ge=1, le=100)
    content_types: list[Literal["image/jpeg", "image/png", "image/webp"]] = []
    orientations: list[Literal["landscape", "portrait", "square"]] = []
    min_width: int | None = Field(default=None, ge=1, le=100_000)
    max_size_bytes: int | None = Field(default=None, ge=1)
    imported_after: str | None = None
    sort: Literal["relevance", "newest", "oldest", "size_desc"] = "relevance"


class SearchHitResponse(BaseModel):
    image_id: str
    score: float | None = Field(default=None, ge=-1, le=1)
    filename: str
    content_type: str
    width: int = 0
    height: int = 0
    size_bytes: int = 0
    created_at: str = ""


class ImportJobResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "completed", "partial", "failed"]
    total_files: int
    processed_files: int
    imported_files: int
    duplicate_files: int
    failed_files: int
    error: str | None
    created_at: str
    updated_at: str


class TemporaryGalleryResponse(BaseModel):
    session_id: str
    status: Literal["queued", "running", "completed", "partial", "failed"]
    total_files: int
    processed_files: int
    imported_files: int
    duplicate_files: int
    failed_files: int
    error: str | None
    created_at: str
    expires_at: str
