from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from collections.abc import Iterator
from uuid import uuid4

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


@dataclass(frozen=True)
class CustomAlbum:
    album_id: str
    name: str
    image_ids: tuple[str, ...]
    created_at: str


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
                    source TEXT NOT NULL DEFAULT 'auto',
                    PRIMARY KEY (image_id, tag),
                    FOREIGN KEY (image_id) REFERENCES images(image_id) ON DELETE CASCADE
                )
                """
            )
            tag_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(image_tags)").fetchall()
            }
            if "source" not in tag_columns:
                connection.execute(
                    "ALTER TABLE image_tags ADD COLUMN source TEXT NOT NULL DEFAULT 'auto'"
                )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS image_tags_tag_idx
                ON image_tags(tag, image_id)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS albums (
                    album_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS album_images (
                    album_id TEXT NOT NULL,
                    image_id TEXT NOT NULL,
                    added_at TEXT NOT NULL,
                    PRIMARY KEY (album_id, image_id),
                    FOREIGN KEY (album_id) REFERENCES albums(album_id) ON DELETE CASCADE,
                    FOREIGN KEY (image_id) REFERENCES images(image_id) ON DELETE CASCADE
                )
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

    def has_manual_tags(self, image_id: str) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM image_tags
                WHERE image_id = ? AND source = 'manual'
                LIMIT 1
                """,
                (image_id,),
            ).fetchone()
        return row is not None

    def list_albums(self) -> list[CustomAlbum]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT album_id, name, created_at FROM albums ORDER BY created_at"
            ).fetchall()
            members = connection.execute(
                "SELECT album_id, image_id FROM album_images ORDER BY added_at"
            ).fetchall()
        image_ids: dict[str, list[str]] = {row["album_id"]: [] for row in rows}
        for member in members:
            image_ids[member["album_id"]].append(member["image_id"])
        return [
            CustomAlbum(
                album_id=row["album_id"],
                name=row["name"],
                image_ids=tuple(image_ids[row["album_id"]]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def create_album(self, name: str) -> CustomAlbum:
        album = CustomAlbum(
            album_id=uuid4().hex,
            name=name,
            image_ids=(),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO albums (album_id, name, created_at) VALUES (?, ?, ?)",
                (album.album_id, album.name, album.created_at),
            )
        return album

    def rename_album(self, album_id: str, name: str) -> CustomAlbum | None:
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE albums SET name = ? WHERE album_id = ?", (name, album_id)
            )
        if cursor.rowcount != 1:
            return None
        return next((album for album in self.list_albums() if album.album_id == album_id), None)

    def delete_album(self, album_id: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM albums WHERE album_id = ?", (album_id,))
        return cursor.rowcount == 1

    def set_album_membership(self, album_id: str, image_id: str, present: bool) -> CustomAlbum:
        with self.connect() as connection:
            if connection.execute(
                "SELECT 1 FROM albums WHERE album_id = ?", (album_id,)
            ).fetchone() is None:
                raise KeyError("album")
            if connection.execute(
                "SELECT 1 FROM images WHERE image_id = ?", (image_id,)
            ).fetchone() is None:
                raise KeyError("image")
            if present:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO album_images (album_id, image_id, added_at)
                    VALUES (?, ?, ?)
                    """,
                    (album_id, image_id, datetime.now(timezone.utc).isoformat()),
                )
            else:
                connection.execute(
                    "DELETE FROM album_images WHERE album_id = ? AND image_id = ?",
                    (album_id, image_id),
                )
        return next(album for album in self.list_albums() if album.album_id == album_id)

    def load_vector(self, image_id: str) -> tuple[np.ndarray, str] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT embedding, embedding_dim, model_id FROM images
                WHERE image_id = ?
                """,
                (image_id,),
            ).fetchone()
        if row is None:
            return None
        return (
            np.frombuffer(
                row["embedding"],
                dtype=np.float32,
                count=row["embedding_dim"],
            ).copy(),
            row["model_id"],
        )

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
            INSERT INTO image_tags (image_id, tag, label, score, model_id, source)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [(image_id, tag.slug, tag.label, tag.score, model_id, tag.source) for tag in tags],
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
            SELECT image_id, tag, label, score, source FROM image_tags
            WHERE image_id IN ({placeholders})
            ORDER BY image_id, score DESC, tag
            """,
            image_ids,
        ).fetchall()
        grouped: dict[str, list[ImageTag]] = {}
        for row in rows:
            grouped.setdefault(row["image_id"], []).append(
                ImageTag(row["tag"], row["label"], row["score"], row["source"])
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
