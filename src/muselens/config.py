import os
from dataclasses import dataclass
from pathlib import Path
import tempfile
from typing import Literal, cast


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LIBRARY_DIR = Path.home() / "Pictures" / "MuseLensLibrary"


def runtime_mode() -> Literal["local", "demo"]:
    default = "demo" if os.getenv("SPACE_ID") else "local"
    value = os.getenv("MUSELENS_MODE", default).strip().lower()
    if value not in {"local", "demo"}:
        raise ValueError("MUSELENS_MODE must be either 'local' or 'demo'.")
    return cast(Literal["local", "demo"], value)


def cors_origins() -> tuple[str, ...]:
    defaults = (
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    )
    value = os.getenv("MUSELENS_CORS_ORIGINS")
    if not value:
        return defaults
    return tuple(origin.strip() for origin in value.split(",") if origin.strip())


@dataclass(frozen=True)
class Settings:
    mode: Literal["local", "demo"] = runtime_mode()
    image_dir: Path = Path(
        os.getenv("MUSELENS_IMAGE_DIR", DEFAULT_LIBRARY_DIR)
    )
    state_dir: Path = Path(
        os.getenv("MUSELENS_STATE_DIR", DEFAULT_LIBRARY_DIR / ".muselens")
    )
    thumbnail_dir: Path = Path(
        os.getenv(
            "MUSELENS_THUMBNAIL_DIR",
            DEFAULT_LIBRARY_DIR / ".muselens" / "thumbnails" / "v1",
        )
    )
    thumbnail_max_size: int = int(os.getenv("MUSELENS_THUMBNAIL_MAX_SIZE", "640"))
    thumbnail_quality: int = int(os.getenv("MUSELENS_THUMBNAIL_QUALITY", "82"))
    clip_model_id: str = os.getenv(
        "MUSELENS_CLIP_MODEL",
        "google/siglip2-base-patch16-224",
    )
    max_upload_mb: int = int(os.getenv("MUSELENS_MAX_UPLOAD_MB", "12"))
    max_image_pixels: int = int(os.getenv("MUSELENS_MAX_IMAGE_PIXELS", "40000000"))
    default_top_k: int = int(os.getenv("MUSELENS_TOP_K", "12"))
    search_min_score: float = float(os.getenv("MUSELENS_SEARCH_MIN_SCORE", "0.12"))
    search_relative_margin: float = float(
        os.getenv("MUSELENS_SEARCH_RELATIVE_MARGIN", "0.035")
    )
    max_batch_files: int = int(os.getenv("MUSELENS_MAX_BATCH_FILES", "100"))
    max_job_files: int = int(os.getenv("MUSELENS_MAX_JOB_FILES", "500"))
    max_job_total_mb: int = int(os.getenv("MUSELENS_MAX_JOB_TOTAL_MB", "512"))
    frontend_dist: Path = Path(
        os.getenv("MUSELENS_FRONTEND_DIST", PROJECT_ROOT / "frontend" / "dist")
    )
    demo_seed_dir: Path | None = (
        Path(value) if (value := os.getenv("MUSELENS_DEMO_SEED_DIR")) else None
    )
    temporary_gallery_dir: Path = Path(
        os.getenv(
            "MUSELENS_TEMP_GALLERY_DIR",
            Path(tempfile.gettempdir()) / "muselens-temporary-galleries",
        )
    )
    temporary_gallery_max_files: int = int(
        os.getenv("MUSELENS_TEMP_GALLERY_MAX_FILES", "30")
    )
    temporary_gallery_max_upload_mb: int = int(
        os.getenv("MUSELENS_TEMP_GALLERY_MAX_UPLOAD_MB", "8")
    )
    temporary_gallery_max_total_mb: int = int(
        os.getenv("MUSELENS_TEMP_GALLERY_MAX_TOTAL_MB", "120")
    )
    temporary_gallery_ttl_seconds: int = int(
        os.getenv("MUSELENS_TEMP_GALLERY_TTL_SECONDS", "1800")
    )
    temporary_gallery_max_sessions: int = int(
        os.getenv("MUSELENS_TEMP_GALLERY_MAX_SESSIONS", "8")
    )
    cors_origins: tuple[str, ...] = cors_origins()


settings = Settings()
