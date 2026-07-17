from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
from threading import Lock, RLock
from uuid import uuid4

from .encoder import ClipEncoder
from .index import VectorIndex
from .library import ImageLibrary, prepare_image
from .repository import ImageRepository


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TemporaryGalleryCapacityError(RuntimeError):
    pass


@dataclass(frozen=True)
class StagedSessionFile:
    filename: str
    content_type: str
    path: Path


@dataclass(frozen=True)
class TemporaryGallerySnapshot:
    session_id: str
    status: str
    total_files: int
    processed_files: int
    imported_files: int
    duplicate_files: int
    failed_files: int
    error: str | None
    created_at: str
    expires_at: str


@dataclass
class TemporaryGallery:
    session_id: str
    directory: Path
    library: ImageLibrary
    index: VectorIndex
    staged_files: list[StagedSessionFile]
    created_at: datetime
    expires_at: datetime
    status: str = "queued"
    processed_files: int = 0
    imported_files: int = 0
    duplicate_files: int = 0
    failed_files: int = 0
    error: str | None = None

    def snapshot(self) -> TemporaryGallerySnapshot:
        return TemporaryGallerySnapshot(
            session_id=self.session_id,
            status=self.status,
            total_files=len(self.staged_files),
            processed_files=self.processed_files,
            imported_files=self.imported_files,
            duplicate_files=self.duplicate_files,
            failed_files=self.failed_files,
            error=self.error,
            created_at=self.created_at.isoformat(),
            expires_at=self.expires_at.isoformat(),
        )


class TemporaryGalleryService:
    def __init__(
        self,
        root: Path,
        encoder: ClipEncoder,
        *,
        ttl_seconds: int = 1800,
        max_upload_bytes: int = 8 * 1024 * 1024,
        max_image_pixels: int = 40_000_000,
        thumbnail_max_size: int = 640,
        thumbnail_quality: int = 82,
        max_sessions: int = 8,
    ) -> None:
        self.root = root
        self.encoder = encoder
        self.ttl_seconds = ttl_seconds
        self.max_upload_bytes = max_upload_bytes
        self.max_image_pixels = max_image_pixels
        self.thumbnail_max_size = thumbnail_max_size
        self.thumbnail_quality = thumbnail_quality
        self.max_sessions = max_sessions
        self._sessions: dict[str, TemporaryGallery] = {}
        self._lock = RLock()
        self._encoder_lock = Lock()

    def initialize(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True, exist_ok=True)

    def new_session_id(self) -> str:
        return uuid4().hex

    def staging_dir(self, session_id: str) -> Path:
        return self.root / session_id / "staging"

    def create(
        self,
        session_id: str,
        staged_files: list[StagedSessionFile],
    ) -> TemporaryGallerySnapshot:
        self.cleanup_expired()
        with self._lock:
            if len(self._sessions) >= self.max_sessions:
                raise TemporaryGalleryCapacityError(
                    "The demo is busy. Please wait for another temporary gallery to expire."
                )
            if session_id in self._sessions:
                raise ValueError("Temporary gallery already exists.")

        directory = self.root / session_id
        repository = ImageRepository(directory / "state" / "index.sqlite3")
        repository.initialize()
        index = VectorIndex()
        library = ImageLibrary(
            directory / "images",
            repository,
            index,
            self.encoder,
            thumbnail_dir=directory / "thumbnails",
            thumbnail_max_size=self.thumbnail_max_size,
            thumbnail_quality=self.thumbnail_quality,
        )
        now = utc_now()
        gallery = TemporaryGallery(
            session_id=session_id,
            directory=directory,
            library=library,
            index=index,
            staged_files=staged_files,
            created_at=now,
            expires_at=now + timedelta(seconds=self.ttl_seconds),
        )
        with self._lock:
            if len(self._sessions) >= self.max_sessions:
                raise TemporaryGalleryCapacityError(
                    "The demo is busy. Please wait for another temporary gallery to expire."
                )
            self._sessions[session_id] = gallery
            return gallery.snapshot()

    def run(self, session_id: str) -> None:
        gallery = self._gallery(session_id)
        with self._encoder_lock:
            with self._lock:
                gallery.status = "running"
            for staged in gallery.staged_files:
                try:
                    candidate = prepare_image(
                        filename=staged.filename,
                        content_type=staged.content_type,
                        content=staged.path.read_bytes(),
                        max_upload_bytes=self.max_upload_bytes,
                        max_image_pixels=self.max_image_pixels,
                    )
                    result = gallery.library.import_candidates([candidate])[0]
                    with self._lock:
                        if result.duplicate:
                            gallery.duplicate_files += 1
                        else:
                            gallery.imported_files += 1
                except Exception as error:
                    with self._lock:
                        gallery.failed_files += 1
                        gallery.error = str(error)
                finally:
                    with self._lock:
                        gallery.processed_files += 1
                    staged.path.unlink(missing_ok=True)

            with self._lock:
                if gallery.failed_files == 0:
                    gallery.status = "completed"
                    gallery.error = None
                elif gallery.failed_files == len(gallery.staged_files):
                    gallery.status = "failed"
                else:
                    gallery.status = "partial"
                gallery.expires_at = utc_now() + timedelta(seconds=self.ttl_seconds)
        shutil.rmtree(gallery.directory / "staging", ignore_errors=True)

    def get(self, session_id: str) -> TemporaryGallerySnapshot:
        self.cleanup_expired()
        with self._lock:
            return self._gallery_unlocked(session_id).snapshot()

    def gallery(self, session_id: str) -> TemporaryGallery:
        self.cleanup_expired()
        with self._lock:
            return self._gallery_unlocked(session_id)

    def delete(self, session_id: str) -> bool:
        with self._lock:
            gallery = self._sessions.get(session_id)
            if gallery and gallery.status in {"queued", "running"}:
                raise RuntimeError("Temporary gallery is still being indexed.")
            gallery = self._sessions.pop(session_id, None)
        if gallery is None:
            return False
        shutil.rmtree(gallery.directory, ignore_errors=True)
        return True

    def cleanup_expired(self, now: datetime | None = None) -> int:
        current = now or utc_now()
        with self._lock:
            expired = [
                session_id
                for session_id, gallery in self._sessions.items()
                if gallery.status not in {"queued", "running"} and gallery.expires_at <= current
            ]
        for session_id in expired:
            self.delete(session_id)
        return len(expired)

    def close(self) -> None:
        with self._lock:
            self._sessions.clear()
        shutil.rmtree(self.root, ignore_errors=True)

    def _gallery(self, session_id: str) -> TemporaryGallery:
        with self._lock:
            return self._gallery_unlocked(session_id)

    def _gallery_unlocked(self, session_id: str) -> TemporaryGallery:
        gallery = self._sessions.get(session_id)
        if gallery is None:
            raise KeyError(session_id)
        return gallery
