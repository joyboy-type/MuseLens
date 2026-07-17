from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

import numpy as np

from .index import IndexedImage


def connect_database(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


@dataclass(frozen=True)
class StoredImage:
    image: IndexedImage
    stored_filename: str
    sha256: str
    size_bytes: int
    model_id: str


class ImageRepository:
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
                CREATE TABLE IF NOT EXISTS images (
                    image_id TEXT PRIMARY KEY,
                    original_filename TEXT NOT NULL,
                    stored_filename TEXT NOT NULL UNIQUE,
                    content_type TEXT NOT NULL,
                    sha256 TEXT NOT NULL UNIQUE,
                    size_bytes INTEGER NOT NULL,
                    embedding BLOB NOT NULL,
                    embedding_dim INTEGER NOT NULL,
                    model_id TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def insert(self, stored: StoredImage, vector: np.ndarray) -> None:
        embedding = np.asarray(vector, dtype=np.float32).reshape(-1)
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO images (
                    image_id, original_filename, stored_filename, content_type,
                    sha256, size_bytes, embedding, embedding_dim, model_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stored.image.image_id,
                    stored.image.filename,
                    stored.stored_filename,
                    stored.image.content_type,
                    stored.sha256,
                    stored.size_bytes,
                    embedding.tobytes(),
                    embedding.size,
                    stored.model_id,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def find_by_sha256(self, digest: str) -> StoredImage | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM images WHERE sha256 = ?",
                (digest,),
            ).fetchone()
        return self._stored_image(row) if row else None

    def find_by_id(self, image_id: str) -> StoredImage | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM images WHERE image_id = ?",
                (image_id,),
            ).fetchone()
        return self._stored_image(row) if row else None

    def load_index(self, model_id: str | None = None) -> list[tuple[StoredImage, np.ndarray]]:
        with self.connect() as connection:
            if model_id is None:
                rows = connection.execute("SELECT * FROM images ORDER BY created_at").fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM images WHERE model_id = ? ORDER BY created_at",
                    (model_id,),
                ).fetchall()
        return [
            (
                self._stored_image(row),
                np.frombuffer(row["embedding"], dtype=np.float32, count=row["embedding_dim"]).copy(),
            )
            for row in rows
        ]

    def replace_embeddings(
        self,
        embeddings: list[tuple[str, np.ndarray]],
        model_id: str,
    ) -> None:
        """Atomically replace all supplied embeddings after encoding succeeds."""
        with self.connect() as connection:
            for image_id, vector in embeddings:
                embedding = np.asarray(vector, dtype=np.float32).reshape(-1)
                cursor = connection.execute(
                    """
                    UPDATE images
                    SET embedding = ?, embedding_dim = ?, model_id = ?
                    WHERE image_id = ?
                    """,
                    (embedding.tobytes(), embedding.size, model_id, image_id),
                )
                if cursor.rowcount != 1:
                    raise KeyError(f"Image {image_id} does not exist.")

    @staticmethod
    def _stored_image(row: sqlite3.Row) -> StoredImage:
        return StoredImage(
            image=IndexedImage(
                image_id=row["image_id"],
                filename=row["original_filename"],
                content_type=row["content_type"],
            ),
            stored_filename=row["stored_filename"],
            sha256=row["sha256"],
            size_bytes=row["size_bytes"],
            model_id=row["model_id"],
        )
