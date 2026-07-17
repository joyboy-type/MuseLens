import numpy as np

from muselens.index import IndexedImage
from muselens.repository import ImageRepository, StoredImage


def test_repository_persists_and_restores_embedding(tmp_path) -> None:
    repository = ImageRepository(tmp_path / "state" / "index.sqlite3")
    repository.initialize()
    stored = StoredImage(
        image=IndexedImage("id-1", "photo.jpg", "image/jpeg"),
        stored_filename="id-1.jpg",
        sha256="abc123",
        size_bytes=42,
        model_id="test-model",
    )
    repository.insert(stored, np.array([0.1, 0.2, 0.3], dtype=np.float32))

    restored = repository.load_index()

    assert len(restored) == 1
    assert restored[0][0] == stored
    np.testing.assert_allclose(restored[0][1], [0.1, 0.2, 0.3])
    assert repository.find_by_sha256("abc123") == stored
    assert repository.find_by_id("id-1") == stored
    assert repository.find_by_id("missing") is None
    assert repository.load_index(model_id="other-model") == []

    with repository.connect() as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 30000


def test_repository_atomically_replaces_embeddings(tmp_path) -> None:
    repository = ImageRepository(tmp_path / "state" / "index.sqlite3")
    repository.initialize()
    stored = StoredImage(
        image=IndexedImage("id-1", "photo.jpg", "image/jpeg"),
        stored_filename="id-1.jpg",
        sha256="abc123",
        size_bytes=42,
        model_id="old-model",
    )
    repository.insert(stored, np.array([0.1, 0.2], dtype=np.float32))

    repository.replace_embeddings(
        [("id-1", np.array([0.3, 0.4, 0.5], dtype=np.float32))],
        "new-model",
    )

    restored = repository.load_index(model_id="new-model")
    assert len(restored) == 1
    assert restored[0][0].model_id == "new-model"
    np.testing.assert_allclose(restored[0][1], [0.3, 0.4, 0.5])
