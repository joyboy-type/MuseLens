from dataclasses import dataclass
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


def create_vector_index(backend: str) -> SearchIndex:
    if backend == "numpy":
        return VectorIndex()
    if backend == "faiss":
        return FaissVectorIndex()
    raise ValueError(f"Unsupported vector index backend: {backend}")
