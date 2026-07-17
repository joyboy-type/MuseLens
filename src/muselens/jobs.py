from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import logging
import shutil
import sqlite3
from threading import Lock
from uuid import uuid4

from .library import ImageLibrary, InvalidImageError, prepare_image
from .repository import connect_database


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StagedFile:
    file_id: str
    filename: str
    content_type: str
    staged_filename: str


@dataclass(frozen=True)
class ImportJob:
    job_id: str
    status: str
    total_files: int
    processed_files: int
    imported_files: int
    duplicate_files: int
    failed_files: int
    error: str | None
    created_at: str
    updated_at: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ImportJobRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def connect(self) -> sqlite3.Connection:
        return connect_database(self.database_path)

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = NORMAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS import_jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    total_files INTEGER NOT NULL,
                    processed_files INTEGER NOT NULL DEFAULT 0,
                    imported_files INTEGER NOT NULL DEFAULT 0,
                    duplicate_files INTEGER NOT NULL DEFAULT 0,
                    failed_files INTEGER NOT NULL DEFAULT 0,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS import_job_files (
                    file_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    original_filename TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    staged_filename TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    duplicate INTEGER NOT NULL DEFAULT 0,
                    error TEXT,
                    FOREIGN KEY (job_id) REFERENCES import_jobs(job_id)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS import_job_files_job_position_idx
                ON import_job_files(job_id, position)
                """
            )

    def recover_interrupted_jobs(self) -> int:
        now = utc_now()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE import_jobs
                SET status = 'failed',
                    error = '服务在任务执行期间中断，请重试。',
                    updated_at = ?
                WHERE status IN ('queued', 'running')
                """,
                (now,),
            )
        return cursor.rowcount

    def create(self, job_id: str, files: list[StagedFile]) -> ImportJob:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO import_jobs (
                    job_id, status, total_files, created_at, updated_at
                ) VALUES (?, 'queued', ?, ?, ?)
                """,
                (job_id, len(files), now, now),
            )
            connection.executemany(
                """
                INSERT INTO import_job_files (
                    file_id, job_id, position, original_filename,
                    content_type, staged_filename
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.file_id,
                        job_id,
                        position,
                        item.filename,
                        item.content_type,
                        item.staged_filename,
                    )
                    for position, item in enumerate(files)
                ],
            )
        job = self.get(job_id)
        if job is None:
            raise RuntimeError("Import job was not persisted.")
        return job

    def get(self, job_id: str) -> ImportJob | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM import_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        return self._job(row) if row else None

    def latest(self) -> ImportJob | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM import_jobs ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        return self._job(row) if row else None

    def pending_files(self, job_id: str) -> list[StagedFile]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM import_job_files
                WHERE job_id = ? AND status = 'pending'
                ORDER BY position
                """,
                (job_id,),
            ).fetchall()
        return [
            StagedFile(
                file_id=row["file_id"],
                filename=row["original_filename"],
                content_type=row["content_type"],
                staged_filename=row["staged_filename"],
            )
            for row in rows
        ]

    def mark_running(self, job_id: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE import_jobs
                SET status = 'running', error = NULL, updated_at = ?
                WHERE job_id = ?
                """,
                (utc_now(), job_id),
            )

    def mark_failed(self, job_id: str, error: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE import_jobs
                SET status = 'failed', error = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (error, utc_now(), job_id),
            )

    def mark_file(
        self,
        file_id: str,
        status: str,
        *,
        duplicate: bool = False,
        error: str | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE import_job_files
                SET status = ?, duplicate = ?, error = ?
                WHERE file_id = ?
                """,
                (status, int(duplicate), error, file_id),
            )

    def sync_progress(self, job_id: str) -> None:
        with self.connect() as connection:
            counts = connection.execute(
                """
                SELECT
                    SUM(CASE WHEN status IN ('completed', 'failed') THEN 1 ELSE 0 END) processed,
                    SUM(CASE WHEN status = 'completed' AND duplicate = 0 THEN 1 ELSE 0 END) imported,
                    SUM(CASE WHEN status = 'completed' AND duplicate = 1 THEN 1 ELSE 0 END) duplicates,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) failed
                FROM import_job_files WHERE job_id = ?
                """,
                (job_id,),
            ).fetchone()
            connection.execute(
                """
                UPDATE import_jobs
                SET processed_files = ?, imported_files = ?, duplicate_files = ?,
                    failed_files = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (
                    counts["processed"] or 0,
                    counts["imported"] or 0,
                    counts["duplicates"] or 0,
                    counts["failed"] or 0,
                    utc_now(),
                    job_id,
                ),
            )

    def finish(self, job_id: str) -> ImportJob:
        self.sync_progress(job_id)
        job = self.get(job_id)
        if job is None:
            raise RuntimeError("Import job disappeared.")
        if job.failed_files == 0:
            status = "completed"
            error = None
        elif job.failed_files == job.total_files:
            status = "failed"
            error = "所有图片处理失败，可以修复问题后重试。"
        else:
            status = "partial"
            error = f"{job.failed_files} 张图片处理失败，可以重试。"
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE import_jobs SET status = ?, error = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (status, error, utc_now(), job_id),
            )
        finished = self.get(job_id)
        if finished is None:
            raise RuntimeError("Import job disappeared.")
        return finished

    def reset_failed(self, job_id: str) -> ImportJob:
        job = self.get(job_id)
        if job is None:
            raise KeyError(job_id)
        if job.status not in {"failed", "partial"}:
            raise ValueError("Only failed or partially completed jobs can be retried.")
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE import_job_files
                SET status = 'pending', error = NULL
                WHERE job_id = ? AND status = 'failed'
                """,
                (job_id,),
            )
            connection.execute(
                """
                UPDATE import_jobs SET status = 'queued', error = NULL, updated_at = ?
                WHERE job_id = ?
                """,
                (utc_now(), job_id),
            )
        self.sync_progress(job_id)
        reset = self.get(job_id)
        if reset is None:
            raise RuntimeError("Import job disappeared.")
        return reset

    @staticmethod
    def _job(row: sqlite3.Row) -> ImportJob:
        return ImportJob(
            job_id=row["job_id"],
            status=row["status"],
            total_files=row["total_files"],
            processed_files=row["processed_files"],
            imported_files=row["imported_files"],
            duplicate_files=row["duplicate_files"],
            failed_files=row["failed_files"],
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class ImportJobService:
    def __init__(
        self,
        staging_dir: Path,
        repository: ImportJobRepository,
        library: ImageLibrary,
        max_upload_bytes: int,
        max_image_pixels: int = 40_000_000,
        batch_size: int = 16,
    ) -> None:
        self.staging_dir = staging_dir
        self.repository = repository
        self.library = library
        self.max_upload_bytes = max_upload_bytes
        self.max_image_pixels = max_image_pixels
        self.batch_size = batch_size
        self._worker_lock = Lock()

    def new_job_id(self) -> str:
        return uuid4().hex

    def run(self, job_id: str) -> None:
        with self._worker_lock:
            try:
                self._run(job_id)
            except Exception as error:
                logger.exception("Import job %s failed unexpectedly", job_id)
                self.repository.mark_failed(job_id, f"后台任务异常：{error}")

    def _run(self, job_id: str) -> None:
        self.repository.mark_running(job_id)
        files = self.repository.pending_files(job_id)
        for start in range(0, len(files), self.batch_size):
            batch = files[start : start + self.batch_size]
            valid_files: list[StagedFile] = []
            candidates = []
            for staged in batch:
                path = self.staging_dir / job_id / staged.staged_filename
                try:
                    candidate = prepare_image(
                        staged.filename,
                        staged.content_type,
                        path.read_bytes(),
                        self.max_upload_bytes,
                        self.max_image_pixels,
                    )
                except (InvalidImageError, OSError) as error:
                    self.repository.mark_file(staged.file_id, "failed", error=str(error))
                else:
                    valid_files.append(staged)
                    candidates.append(candidate)

            if candidates:
                try:
                    results = self.library.import_candidates(candidates)
                except Exception as error:
                    for staged in valid_files:
                        self.repository.mark_file(
                            staged.file_id,
                            "failed",
                            error=f"Indexing failed: {error}",
                        )
                else:
                    for staged, result in zip(valid_files, results, strict=True):
                        self.repository.mark_file(
                            staged.file_id,
                            "completed",
                            duplicate=result.duplicate,
                        )
                        (self.staging_dir / job_id / staged.staged_filename).unlink(
                            missing_ok=True
                        )
            self.repository.sync_progress(job_id)

        finished = self.repository.finish(job_id)
        if finished.status == "completed":
            shutil.rmtree(self.staging_dir / job_id, ignore_errors=True)
