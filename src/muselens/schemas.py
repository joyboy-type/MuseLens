from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    status: str
    indexed_images: int
    model_loaded: bool


class ImageRecordResponse(BaseModel):
    image_id: str
    filename: str
    content_type: str


class ImportResponse(ImageRecordResponse):
    duplicate: bool
    sha256: str


class TextSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=300)
    top_k: int = Field(default=12, ge=1, le=100)


class SearchHitResponse(BaseModel):
    image_id: str
    score: float = Field(ge=-1, le=1)
    filename: str


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
