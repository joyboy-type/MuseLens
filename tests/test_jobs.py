from io import BytesIO

import numpy as np
from PIL import Image

from muselens.index import VectorIndex
from muselens.jobs import ImportJobRepository, ImportJobService, StagedFile
from muselens.library import ImageLibrary
from muselens.repository import ImageRepository


class FakeEncoder:
    model_id = "fake-encoder"

    def encode_images(self, images):
        return np.tile(np.array([[1.0, 0.0]], dtype=np.float32), (len(images), 1))


def jpeg_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (24, 16), "green").save(buffer, format="JPEG")
    return buffer.getvalue()


def test_import_job_tracks_partial_progress_and_retries_failed_files(tmp_path) -> None:
    database = tmp_path / "state" / "index.sqlite3"
    image_repository = ImageRepository(database)
    image_repository.initialize()
    library = ImageLibrary(
        tmp_path / "images",
        image_repository,
        VectorIndex(),
        FakeEncoder(),
    )
    job_repository = ImportJobRepository(database)
    job_repository.initialize()
    service = ImportJobService(
        tmp_path / "jobs",
        job_repository,
        library,
        max_upload_bytes=1024 * 1024,
    )
    job_id = service.new_job_id()
    job_dir = service.staging_dir / job_id
    job_dir.mkdir(parents=True)
    (job_dir / "valid.jpg").write_bytes(jpeg_bytes())
    (job_dir / "broken.jpg").write_bytes(b"not an image")
    files = [
        StagedFile("file-1", "valid.jpg", "image/jpeg", "valid.jpg"),
        StagedFile("file-2", "broken.jpg", "image/jpeg", "broken.jpg"),
    ]
    job_repository.create(job_id, files)

    service.run(job_id)

    partial = job_repository.get(job_id)
    assert partial is not None
    assert partial.status == "partial"
    assert partial.processed_files == 2
    assert partial.imported_files == 1
    assert partial.failed_files == 1

    (job_dir / "broken.jpg").write_bytes(jpeg_bytes())
    reset = job_repository.reset_failed(job_id)
    assert reset.status == "queued"
    assert reset.processed_files == 1

    service.run(job_id)

    completed = job_repository.get(job_id)
    assert completed is not None
    assert completed.status == "completed"
    assert completed.processed_files == 2
    assert completed.imported_files == 1
    assert completed.duplicate_files == 1
    assert completed.failed_files == 0
    assert not job_dir.exists()


def test_repository_recovers_an_interrupted_job_as_retryable(tmp_path) -> None:
    database = tmp_path / "state" / "index.sqlite3"
    ImageRepository(database).initialize()
    repository = ImportJobRepository(database)
    repository.initialize()
    job_id = "interrupted"
    repository.create(
        job_id,
        [StagedFile("file-1", "photo.jpg", "image/jpeg", "photo.jpg")],
    )
    repository.mark_running(job_id)

    assert repository.recover_interrupted_jobs() == 1
    recovered = repository.get(job_id)
    assert recovered is not None
    assert recovered.status == "failed"
    assert "重试" in (recovered.error or "")


def test_unexpected_worker_error_is_persisted_as_failed(tmp_path, monkeypatch) -> None:
    database = tmp_path / "state" / "index.sqlite3"
    image_repository = ImageRepository(database)
    image_repository.initialize()
    library = ImageLibrary(
        tmp_path / "images",
        image_repository,
        VectorIndex(),
        FakeEncoder(),
    )
    repository = ImportJobRepository(database)
    repository.initialize()
    job_id = "unexpected"
    repository.create(
        job_id,
        [StagedFile("file-1", "photo.jpg", "image/jpeg", "photo.jpg")],
    )
    service = ImportJobService(
        tmp_path / "jobs",
        repository,
        library,
        max_upload_bytes=1024 * 1024,
    )
    monkeypatch.setattr(
        repository,
        "pending_files",
        lambda _: (_ for _ in ()).throw(RuntimeError("database unavailable")),
    )

    service.run(job_id)

    failed = repository.get(job_id)
    assert failed is not None
    assert failed.status == "failed"
    assert "database unavailable" in (failed.error or "")
