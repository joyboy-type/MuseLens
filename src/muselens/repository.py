from dataclasses import dataclass
from pathlib import Path
import sqlite3
from collections.abc import Iterator

import numpy as np

from .index import IndexedImage
from .tags import ImageTag


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
    width: int = 0
    height: int = 0
    created_at: str = ""
    perceptual_hash: str = ""
    average_color: str = ""
    tags: tuple[ImageTag, ...] = ()


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
                    width INTEGER NOT NULL DEFAULT 0,
                    height INTEGER NOT NULL DEFAULT 0,
                    embedding BLOB NOT NULL,
                    embedding_dim INTEGER NOT NULL,
                    model_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    perceptual_hash TEXT NOT NULL DEFAULT '',
                    average_color TEXT NOT NULL DEFAULT ''
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS image_tags (
                    image_id TEXT NOT NULL,
                    tag TEXT NOT NULL,
                    label TEXT NOT NULL,
                    score REAL NOT NULL,
                    model_id TEXT NOT NULL,
                    PRIMARY KEY (image_id, tag),
                    FOREIGN KEY (image_id) REFERENCES images(image_id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS image_tags_tag_idx
                ON image_tags(tag, image_id)
                """
            )
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(images)").fetchall()
            }
            if "width" not in columns:
                connection.execute("ALTER TABLE images ADD COLUMN width INTEGER NOT NULL DEFAULT 0")
            if "height" not in columns:
                connection.execute(
                    "ALTER TABLE images ADD COLUMN height INTEGER NOT NULL DEFAULT 0"
                )
            if "perceptual_hash" not in columns:
                connection.execute(
                    "ALTER TABLE images ADD COLUMN perceptual_hash TEXT NOT NULL DEFAULT ''"
                )
            if "average_color" not in columns:
                connection.execute(
                    "ALTER TABLE images ADD COLUMN average_color TEXT NOT NULL DEFAULT ''"
                )

    def insert(
        self,
        stored: StoredImage,
        vector: np.ndarray,
        tag_model_id: str = "",
    ) -> None:
        embedding = np.asarray(vector, dtype=np.float32).reshape(-1)
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO images (
                    image_id, original_filename, stored_filename, content_type,
                    sha256, size_bytes, width, height, embedding, embedding_dim, model_id, created_at,
                    perceptual_hash, average_color
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stored.image.image_id,
                    stored.image.filename,
                    stored.stored_filename,
                    stored.image.content_type,
                    stored.sha256,
                    stored.size_bytes,
                    stored.width,
                    stored.height,
                    embedding.tobytes(),
                    embedding.size,
                    stored.model_id,
                    stored.created_at,
                    stored.perceptual_hash,
                    stored.average_color,
                ),
            )
            self._replace_tags(connection, stored.image.image_id, stored.tags, tag_model_id)

    def replace_tags(
        self,
        image_id: str,
        tags: tuple[ImageTag, ...],
        model_id: str,
    ) -> None:
        with self.connect() as connection:
            self._replace_tags(connection, image_id, tags, model_id)

    def update_dimensions(self, image_id: str, width: int, height: int) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE images SET width = ?, height = ? WHERE image_id = ?",
                (width, height, image_id),
            )

    def update_visual_fingerprint(
        self,
        image_id: str,
        perceptual_hash: str,
        average_color: str,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE images
                SET perceptual_hash = ?, average_color = ?
                WHERE image_id = ?
                """,
                (perceptual_hash, average_color, image_id),
            )

    def delete(self, image_id: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM images WHERE image_id = ?", (image_id,))
        return cursor.rowcount == 1

    def list_stored(self) -> list[StoredImage]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM images ORDER BY created_at DESC").fetchall()
            tags = self._tags_by_image(connection, [row["image_id"] for row in rows])
        return [self._stored_image(row, tags.get(row["image_id"], ())) for row in rows]

    def find_by_sha256(self, digest: str) -> StoredImage | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM images WHERE sha256 = ?",
                (digest,),
            ).fetchone()
            tags = self._tags_by_image(connection, [row["image_id"]]) if row else {}
        return self._stored_image(row, tags.get(row["image_id"], ())) if row else None

    def find_by_id(self, image_id: str) -> StoredImage | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM images WHERE image_id = ?",
                (image_id,),
            ).fetchone()
            tags = self._tags_by_image(connection, [image_id]) if row else {}
        return self._stored_image(row, tags.get(image_id, ())) if row else None

    def load_index(self, model_id: str | None = None) -> list[tuple[StoredImage, np.ndarray]]:
        return list(self.iter_index(model_id=model_id))

    def iter_index(
        self,
        model_id: str | None = None,
        batch_size: int = 512,
    ) -> Iterator[tuple[StoredImage, np.ndarray]]:
        """Stream persisted vectors so startup memory does not scale with library size."""
        if batch_size < 1:
            raise ValueError("batch_size must be positive.")
        with self.connect() as connection:
            if model_id is None:
                cursor = connection.execute("SELECT * FROM images ORDER BY created_at")
            else:
                cursor = connection.execute(
                    "SELECT * FROM images WHERE model_id = ? ORDER BY created_at",
                    (model_id,),
                )
            while rows := cursor.fetchmany(batch_size):
                for row in rows:
                    yield (
                        self._stored_image(row),
                        np.frombuffer(
                            row["embedding"],
                            dtype=np.float32,
                            count=row["embedding_dim"],
                        ).copy(),
                    )

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
    def _replace_tags(
        connection: sqlite3.Connection,
        image_id: str,
        tags: tuple[ImageTag, ...],
        model_id: str,
    ) -> None:
        connection.execute("DELETE FROM image_tags WHERE image_id = ?", (image_id,))
        connection.executemany(
            """
            INSERT INTO image_tags (image_id, tag, label, score, model_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            [(image_id, tag.slug, tag.label, tag.score, model_id) for tag in tags],
        )

    @staticmethod
    def _tags_by_image(
        connection: sqlite3.Connection,
        image_ids: list[str],
    ) -> dict[str, tuple[ImageTag, ...]]:
        if not image_ids:
            return {}
        placeholders = ",".join("?" for _ in image_ids)
        rows = connection.execute(
            f"""
            SELECT image_id, tag, label, score FROM image_tags
            WHERE image_id IN ({placeholders})
            ORDER BY image_id, score DESC, tag
            """,
            image_ids,
        ).fetchall()
        grouped: dict[str, list[ImageTag]] = {}
        for row in rows:
            grouped.setdefault(row["image_id"], []).append(
                ImageTag(row["tag"], row["label"], row["score"])
            )
        return {image_id: tuple(tags) for image_id, tags in grouped.items()}

    @staticmethod
    def _stored_image(
        row: sqlite3.Row,
        tags: tuple[ImageTag, ...] = (),
    ) -> StoredImage:
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
            width=row["width"],
            height=row["height"],
            created_at=row["created_at"],
            perceptual_hash=row["perceptual_hash"],
            average_color=row["average_color"],
            tags=tags,
        )
