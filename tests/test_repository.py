import numpy as np

from muselens.index import IndexedImage
from muselens.repository import ImageRepository, StoredImage
from muselens.tags import ImageTag


def test_repository_persists_and_restores_embedding(tmp_path) -> None:
    repository = ImageRepository(tmp_path / "state" / "index.sqlite3")
    repository.initialize()
    stored = StoredImage(
        image=IndexedImage("id-1", "photo.jpg", "image/jpeg"),
        stored_filename="id-1.jpg",
        sha256="abc123",
        size_bytes=42,
        model_id="test-model",
        perceptual_hash="0123456789abcdef",
        average_color="aabbcc",
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
    streamed = list(repository.iter_index(batch_size=1))
    assert [item[0].image.image_id for item in streamed] == ["id-1"]
    np.testing.assert_allclose(streamed[0][1], [0.1, 0.2, 0.3])

    with repository.connect() as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 30000


def test_repository_migrates_and_updates_visual_fingerprints(tmp_path) -> None:
    database = tmp_path / "state" / "index.sqlite3"
    database.parent.mkdir(parents=True)
    import sqlite3

    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE images (
                image_id TEXT PRIMARY KEY,
                original_filename TEXT NOT NULL,
                stored_filename TEXT NOT NULL UNIQUE,
                content_type TEXT NOT NULL,
                sha256 TEXT NOT NULL UNIQUE,
                size_bytes INTEGER NOT NULL,
                width INTEGER NOT NULL DEFAULT 0,
                height INTEGER NOT NULL DEFAULT 0,
                embedding BLOB NOT NULL,
                embedding_dim INTEGER NOT NULL,
                model_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
    repository = ImageRepository(database)
    repository.initialize()
    stored = StoredImage(
        image=IndexedImage("id-1", "photo.jpg", "image/jpeg"),
        stored_filename="id-1.jpg",
        sha256="digest",
        size_bytes=12,
        model_id="model",
    )
    repository.insert(stored, np.asarray([1.0, 0.0], dtype=np.float32))

    repository.update_visual_fingerprint("id-1", "fedcba9876543210", "112233")

    restored = repository.find_by_id("id-1")
    assert restored is not None
    assert restored.perceptual_hash == "fedcba9876543210"
    assert restored.average_color == "112233"


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


def test_repository_persists_replaces_and_cascades_image_tags(tmp_path) -> None:
    repository = ImageRepository(tmp_path / "state" / "index.sqlite3")
    repository.initialize()
    stored = StoredImage(
        image=IndexedImage("id-1", "dog.jpg", "image/jpeg"),
        stored_filename="id-1.jpg",
        sha256="dog-digest",
        size_bytes=42,
        model_id="vision-model",
        tags=(ImageTag("dog", "狗", 0.81),),
    )
    repository.insert(stored, np.asarray([1.0, 0.0], dtype=np.float32), "tagger-v1")

    assert repository.find_by_id("id-1").tags == (ImageTag("dog", "狗", 0.81),)

    repository.replace_tags("id-1", (ImageTag("pet", "宠物", 0.76),), "tagger-v2")
    assert repository.list_stored()[0].tags == (ImageTag("pet", "宠物", 0.76),)

    assert repository.delete("id-1") is True
    with repository.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM image_tags").fetchone()[0] == 0
