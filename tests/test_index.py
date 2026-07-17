import sys

import numpy as np
import pytest

from muselens.index import (
    FaissVectorIndex,
    IndexedImage,
    SearchHit,
    VectorIndex,
    create_vector_index,
    filter_relevant_hits,
)


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


def test_matrix_index_preserves_insertion_order_for_equal_scores() -> None:
    index = VectorIndex()
    index.add(IndexedImage("first", "first.jpg", "image/jpeg"), np.array([1.0, 0.0]))
    index.add(IndexedImage("second", "second.jpg", "image/jpeg"), np.array([1.0, 0.0]))

    hits = index.search(np.array([1.0, 0.0]), top_k=10)

    assert [hit.image.image_id for hit in hits] == ["first", "second"]


def test_matrix_cache_is_rebuilt_after_an_image_is_added() -> None:
    index = VectorIndex()
    index.add(IndexedImage("first", "first.jpg", "image/jpeg"), np.array([1.0, 0.0]))
    assert [hit.image.image_id for hit in index.search(np.array([0.0, 1.0]), 10)] == [
        "first"
    ]

    index.add(IndexedImage("second", "second.jpg", "image/jpeg"), np.array([0.0, 1.0]))
    hits = index.search(np.array([0.0, 1.0]), top_k=10)

    assert [hit.image.image_id for hit in hits] == ["second", "first"]


def test_faiss_exact_index_matches_numpy_rankings_and_scores() -> None:
    pytest.importorskip("faiss")
    if sys.platform == "darwin" and "torch" in sys.modules:
        pytest.skip("pip FAISS and PyTorch wheels conflict on macOS")
    numpy_index = VectorIndex()
    faiss_index = FaissVectorIndex()
    rng = np.random.default_rng(7)
    for position, vector in enumerate(rng.normal(size=(50, 16))):
        image = IndexedImage(str(position), f"{position}.jpg", "image/jpeg")
        numpy_index.add(image, vector)
        faiss_index.add(image, vector)

    query = rng.normal(size=16)
    numpy_hits = numpy_index.search(query, 10)
    faiss_hits = faiss_index.search(query, 10)

    assert [hit.image.image_id for hit in faiss_hits] == [
        hit.image.image_id for hit in numpy_hits
    ]
    np.testing.assert_allclose(
        [hit.score for hit in faiss_hits],
        [hit.score for hit in numpy_hits],
        atol=1e-6,
    )


def test_index_factory_rejects_unknown_backends() -> None:
    assert isinstance(create_vector_index("numpy"), VectorIndex)
    with pytest.raises(ValueError, match="Unsupported"):
        create_vector_index("unknown")


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


def test_relative_only_filter_never_discards_the_best_match() -> None:
    image = IndexedImage("one", "one.jpg", "image/jpeg")
    hits = [SearchHit(image, 0.07), SearchHit(image, 0.02)]

    filtered = filter_relevant_hits(hits, None, 0.035, 12)

    assert [hit.score for hit in filtered] == [0.07]
