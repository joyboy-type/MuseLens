from dataclasses import dataclass
from pathlib import Path
import sys
from threading import RLock
from typing import Any, Protocol

import numpy as np


@dataclass(frozen=True)
class IndexedImage:
    image_id: str
    filename: str
    content_type: str


@dataclass(frozen=True)
class SearchHit:
    image: IndexedImage
    score: float


class SearchIndex(Protocol):
    def __len__(self) -> int: ...

    def add(self, image: IndexedImage, vector: np.ndarray) -> None: ...

    def remove(self, image_id: str) -> bool: ...

    def clear(self) -> None: ...

    def search(self, query: np.ndarray, top_k: int) -> list[SearchHit]: ...

    def list_images(self) -> list[IndexedImage]: ...


def filter_relevant_hits(
    hits: list[SearchHit],
    absolute_floor: float | None,
    relative_margin: float,
    max_results: int,
) -> list[SearchHit]:
    """Drop weak nearest neighbours instead of always returning the whole library."""
    if not hits or (absolute_floor is not None and hits[0].score < absolute_floor):
        return []
    threshold = hits[0].score - relative_margin
    if absolute_floor is not None:
        threshold = max(absolute_floor, threshold)
    return [hit for hit in hits if hit.score >= threshold][:max_results]


def normalize(vector: np.ndarray) -> np.ndarray:
    values = np.asarray(vector, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(values))
    if norm == 0:
        raise ValueError("Cannot index a zero embedding.")
    return values / norm


class VectorIndex:
    """Exact cosine index backed by one contiguous NumPy matrix."""

    def __init__(self) -> None:
        self._vectors: dict[str, np.ndarray] = {}
        self._images: dict[str, IndexedImage] = {}
        self._dimension: int | None = None
        self._matrix: np.ndarray | None = None
        self._ordered_ids: tuple[str, ...] = ()
        self._lock = RLock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._images)

    def add(self, image: IndexedImage, vector: np.ndarray) -> None:
        embedding = normalize(vector)
        with self._lock:
            if self._dimension is None:
                self._dimension = embedding.size
            if embedding.size != self._dimension:
                raise ValueError(
                    f"Embedding dimension {embedding.size} does not match {self._dimension}."
                )
            self._images[image.image_id] = image
            self._vectors[image.image_id] = embedding
            self._matrix = None
            self._ordered_ids = ()

    def clear(self) -> None:
        with self._lock:
            self._vectors.clear()
            self._images.clear()
            self._dimension = None
            self._matrix = None
            self._ordered_ids = ()

    def remove(self, image_id: str) -> bool:
        with self._lock:
            existed = image_id in self._images
            self._images.pop(image_id, None)
            self._vectors.pop(image_id, None)
            if existed:
                self._matrix = None
                self._ordered_ids = ()
                if not self._images:
                    self._dimension = None
            return existed

    def search(self, query: np.ndarray, top_k: int) -> list[SearchHit]:
        normalized_query = normalize(query)
        with self._lock:
            if not self._vectors:
                return []
            if normalized_query.size != self._dimension:
                raise ValueError("Query embedding dimension does not match the index.")
            if self._matrix is None:
                self._ordered_ids = tuple(self._vectors)
                self._matrix = np.ascontiguousarray(
                    np.stack([self._vectors[image_id] for image_id in self._ordered_ids]),
                    dtype=np.float32,
                )
            scores = self._matrix @ normalized_query
            # A stable sort preserves insertion order for equal scores, matching the
            # original exact implementation and keeping tests and UI deterministic.
            positions = np.argsort(-scores, kind="stable")[: min(top_k, scores.size)]
            return [
                SearchHit(
                    image=self._images[self._ordered_ids[position]],
                    score=float(scores[position]),
                )
                for position in positions
            ]

    def list_images(self) -> list[IndexedImage]:
        with self._lock:
            return list(self._images.values())


class MmapVectorIndex:
    """Exact cosine index whose contiguous vector matrix is backed by a file.

    SQLite remains the source of truth. The mmap file is a disposable search
    cache rebuilt at process startup, so a partial cache can never corrupt the
    user's image library.
    """

    def __init__(
        self,
        storage_path: Path,
        search_chunk_rows: int = 8192,
        remove_on_close: bool = True,
    ) -> None:
        if search_chunk_rows < 1:
            raise ValueError("search_chunk_rows must be positive.")
        self.storage_path = storage_path
        self.search_chunk_rows = search_chunk_rows
        self.remove_on_close = remove_on_close
        self._images: dict[str, IndexedImage] = {}
        self._positions: dict[str, int] = {}
        self._row_ids: list[str | None] = []
        self._dimension: int | None = None
        self._lock = RLock()
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.storage_path.open("w+b")

    def __len__(self) -> int:
        with self._lock:
            return len(self._images)

    def add(self, image: IndexedImage, vector: np.ndarray) -> None:
        embedding = normalize(vector)
        with self._lock:
            if self._dimension is None:
                self._dimension = embedding.size
            if embedding.size != self._dimension:
                raise ValueError(
                    f"Embedding dimension {embedding.size} does not match {self._dimension}."
                )
            existing_position = self._positions.get(image.image_id)
            if existing_position is None:
                position = len(self._row_ids)
                self._file.seek(0, 2)
                self._file.write(embedding.tobytes())
                self._row_ids.append(image.image_id)
                self._positions[image.image_id] = position
            else:
                offset = existing_position * self._dimension * np.dtype(np.float32).itemsize
                self._file.seek(offset)
                self._file.write(embedding.tobytes())
            self._images[image.image_id] = image

    def clear(self) -> None:
        with self._lock:
            self._file.close()
            self._file = self.storage_path.open("w+b")
            self._images.clear()
            self._positions.clear()
            self._row_ids.clear()
            self._dimension = None

    def close(self) -> None:
        with self._lock:
            if not self._file.closed:
                self._file.close()
            if self.remove_on_close:
                self.storage_path.unlink(missing_ok=True)

    def remove(self, image_id: str) -> bool:
        with self._lock:
            position = self._positions.pop(image_id, None)
            if position is None:
                return False
            self._row_ids[position] = None
            self._images.pop(image_id, None)
            if not self._images:
                self.clear()
            return True

    def search(self, query: np.ndarray, top_k: int) -> list[SearchHit]:
        normalized_query = normalize(query)
        with self._lock:
            if not self._images:
                return []
            if normalized_query.size != self._dimension:
                raise ValueError("Query embedding dimension does not match the index.")
            self._file.flush()
            matrix = np.memmap(
                self.storage_path,
                dtype=np.float32,
                mode="r",
                shape=(len(self._row_ids), self._dimension),
            )
            scores = np.full(len(self._row_ids), -np.inf, dtype=np.float32)
            try:
                for start in range(0, len(self._row_ids), self.search_chunk_rows):
                    end = min(start + self.search_chunk_rows, len(self._row_ids))
                    block_scores = matrix[start:end] @ normalized_query
                    active = np.fromiter(
                        (image_id is not None for image_id in self._row_ids[start:end]),
                        dtype=np.bool_,
                        count=end - start,
                    )
                    scores[start:end][active] = block_scores[active]
            finally:
                del matrix

            positions = np.argsort(-scores, kind="stable")[: min(top_k, len(self._images))]
            return [
                SearchHit(
                    image=self._images[image_id],
                    score=float(scores[position]),
                )
                for position in positions
                if (image_id := self._row_ids[int(position)]) is not None
            ]

    def list_images(self) -> list[IndexedImage]:
        with self._lock:
            return list(self._images.values())


class FaissVectorIndex:
    """Optional exact cosine index using Faiss IndexFlatIP."""

    def __init__(self) -> None:
        if sys.platform == "darwin" and "torch" in sys.modules:
            raise RuntimeError(
                "The pip FAISS and PyTorch wheels bundle conflicting OpenMP runtimes on "
                "macOS. Use MUSELENS_INDEX_BACKEND=numpy in the application; run FAISS "
                "only through the isolated index benchmark."
            )
        try:
            import faiss
        except ImportError as error:
            raise RuntimeError(
                "The FAISS backend requires the optional dependency: "
                "python -m pip install -e '.[faiss]'"
            ) from error
        self._faiss: Any = faiss
        self._vectors: dict[str, np.ndarray] = {}
        self._images: dict[str, IndexedImage] = {}
        self._dimension: int | None = None
        self._index: Any | None = None
        self._ordered_ids: tuple[str, ...] = ()
        self._lock = RLock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._images)

    def add(self, image: IndexedImage, vector: np.ndarray) -> None:
        embedding = normalize(vector)
        with self._lock:
            if self._dimension is None:
                self._dimension = embedding.size
            if embedding.size != self._dimension:
                raise ValueError(
                    f"Embedding dimension {embedding.size} does not match {self._dimension}."
                )
            self._images[image.image_id] = image
            self._vectors[image.image_id] = embedding
            self._index = None
            self._ordered_ids = ()

    def clear(self) -> None:
        with self._lock:
            self._vectors.clear()
            self._images.clear()
            self._dimension = None
            self._index = None
            self._ordered_ids = ()

    def remove(self, image_id: str) -> bool:
        with self._lock:
            existed = image_id in self._images
            self._images.pop(image_id, None)
            self._vectors.pop(image_id, None)
            if existed:
                self._index = None
                self._ordered_ids = ()
                if not self._images:
                    self._dimension = None
            return existed

    def search(self, query: np.ndarray, top_k: int) -> list[SearchHit]:
        normalized_query = normalize(query)
        with self._lock:
            if not self._vectors:
                return []
            if normalized_query.size != self._dimension:
                raise ValueError("Query embedding dimension does not match the index.")
            if self._index is None:
                self._ordered_ids = tuple(self._vectors)
                matrix = np.ascontiguousarray(
                    np.stack([self._vectors[image_id] for image_id in self._ordered_ids]),
                    dtype=np.float32,
                )
                self._index = self._faiss.IndexFlatIP(self._dimension)
                self._index.add(matrix)
            limit = min(top_k, len(self._ordered_ids))
            scores, positions = self._index.search(normalized_query.reshape(1, -1), limit)
            return [
                SearchHit(
                    image=self._images[self._ordered_ids[int(position)]],
                    score=float(score),
                )
                for score, position in zip(scores[0], positions[0], strict=True)
                if position >= 0
            ]

    def list_images(self) -> list[IndexedImage]:
        with self._lock:
            return list(self._images.values())


def create_vector_index(backend: str, storage_path: Path | None = None) -> SearchIndex:
    if backend == "numpy":
        return VectorIndex()
    if backend == "mmap":
        if storage_path is None:
            raise ValueError("The mmap backend requires a storage path.")
        return MmapVectorIndex(storage_path)
    if backend == "faiss":
        return FaissVectorIndex()
    raise ValueError(f"Unsupported vector index backend: {backend}")
