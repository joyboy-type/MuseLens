import numpy as np
import pytest

from muselens.index import IndexedImage, SearchHit, VectorIndex, filter_relevant_hits


def test_cosine_search_returns_most_similar_image_first() -> None:
    index = VectorIndex()
    index.add(IndexedImage("red", "red.jpg", "image/jpeg"), np.array([1.0, 0.0]))
    index.add(IndexedImage("blue", "blue.jpg", "image/jpeg"), np.array([0.0, 1.0]))

    hits = index.search(np.array([0.9, 0.1]), top_k=2)

    assert [hit.image.image_id for hit in hits] == ["red", "blue"]
    assert hits[0].score > hits[1].score


def test_index_rejects_inconsistent_dimensions() -> None:
    index = VectorIndex()
    index.add(IndexedImage("one", "one.jpg", "image/jpeg"), np.array([1.0, 0.0]))
    with pytest.raises(ValueError, match="dimension"):
        index.add(IndexedImage("two", "two.jpg", "image/jpeg"), np.ones(3))


def test_relevance_filter_rejects_an_unrelated_query() -> None:
    image = IndexedImage("one", "one.jpg", "image/jpeg")
    hits = [SearchHit(image, 0.20), SearchHit(image, 0.19)]
    assert filter_relevant_hits(hits, 0.22, 0.035, 12) == []


def test_relevance_filter_keeps_only_the_strong_cluster() -> None:
    image = IndexedImage("one", "one.jpg", "image/jpeg")
    hits = [
        SearchHit(image, 0.29),
        SearchHit(image, 0.28),
        SearchHit(image, 0.26),
        SearchHit(image, 0.20),
        SearchHit(image, 0.18),
    ]
    filtered = filter_relevant_hits(hits, 0.22, 0.035, 12)
    assert [hit.score for hit in filtered] == [0.29, 0.28, 0.26]
