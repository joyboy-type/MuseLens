from dataclasses import dataclass
from threading import RLock

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


def filter_relevant_hits(
    hits: list[SearchHit],
    absolute_floor: float,
    relative_margin: float,
    max_results: int,
) -> list[SearchHit]:
    """Drop weak nearest neighbours instead of always returning the whole library."""
    if not hits or hits[0].score < absolute_floor:
        return []
    threshold = max(
        absolute_floor,
        hits[0].score - relative_margin,
    )
    return [hit for hit in hits if hit.score >= threshold][:max_results]


def normalize(vector: np.ndarray) -> np.ndarray:
    values = np.asarray(vector, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(values))
    if norm == 0:
        raise ValueError("Cannot index a zero embedding.")
    return values / norm


class VectorIndex:
    """Small in-memory cosine index; later replaced by FAISS/Qdrant behind this interface."""

    def __init__(self) -> None:
        self._vectors: dict[str, np.ndarray] = {}
        self._images: dict[str, IndexedImage] = {}
        self._dimension: int | None = None
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

    def clear(self) -> None:
        with self._lock:
            self._vectors.clear()
            self._images.clear()
            self._dimension = None

    def search(self, query: np.ndarray, top_k: int) -> list[SearchHit]:
        normalized_query = normalize(query)
        with self._lock:
            if not self._vectors:
                return []
            if normalized_query.size != self._dimension:
                raise ValueError("Query embedding dimension does not match the index.")
            scored = [
                SearchHit(image=self._images[image_id], score=float(vector @ normalized_query))
                for image_id, vector in self._vectors.items()
            ]
        return sorted(scored, key=lambda hit: hit.score, reverse=True)[:top_k]

    def list_images(self) -> list[IndexedImage]:
        with self._lock:
            return list(self._images.values())
