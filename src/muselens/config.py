import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LIBRARY_DIR = Path.home() / "Pictures" / "MuseLensLibrary"


@dataclass(frozen=True)
class Settings:
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


settings = Settings()
