from types import SimpleNamespace

import numpy as np
from pydantic import ValidationError
import pytest

from muselens.api import matches_search_filters, search_by_text, sort_filtered_results
from muselens.index import IndexedImage, SearchHit
from muselens.repository import StoredImage
from muselens.schemas import TextSearchRequest
from muselens.tags import ImageTag


def stored_image(
    image_id: str,
    content_type: str,
    width: int,
    height: int,
    size_bytes: int,
    created_at: str,
) -> StoredImage:
    return StoredImage(
        image=IndexedImage(image_id, f"{image_id}.jpg", content_type),
        stored_filename=f"{image_id}.jpg",
        sha256=image_id,
        size_bytes=size_bytes,
        model_id="test",
        width=width,
        height=height,
        created_at=created_at,
    )


def test_combined_metadata_filters_are_all_enforced() -> None:
    landscape = stored_image(
        "wide", "image/jpeg", 2400, 1200, 2_000_000, "2026-07-10T00:00:00+00:00"
    )
    payload = TextSearchRequest(
        content_types=["image/jpeg"],
        orientations=["landscape"],
        min_width=1920,
        max_size_bytes=3_000_000,
        imported_after="2026-07-01T00:00:00+00:00",
    )

    assert matches_search_filters(landscape, payload)
    assert not matches_search_filters(
        stored_image("portrait", "image/jpeg", 1200, 2400, 2_000_000, "2026-07-10T00:00:00+00:00"),
        payload,
    )


def test_metadata_results_support_newest_and_size_sorting() -> None:
    older_large = stored_image(
        "older", "image/png", 1000, 1000, 5_000_000, "2026-06-01T00:00:00+00:00"
    )
    newer_small = stored_image(
        "newer", "image/png", 1000, 1000, 1_000_000, "2026-07-01T00:00:00+00:00"
    )
    results = [(None, older_large), (None, newer_small)]

    assert sort_filtered_results(results, "newest")[0][1].image.image_id == "newer"
    assert sort_filtered_results(results, "size_desc")[0][1].image.image_id == "older"


def test_tag_filter_matches_any_selected_semantic_tag() -> None:
    tagged = stored_image("pet", "image/jpeg", 1000, 800, 1_000_000, "2026-07-01T00:00:00+00:00")
    tagged = StoredImage(**{**vars(tagged), "tags": (ImageTag("dog", "狗", 0.8),)})

    assert matches_search_filters(tagged, TextSearchRequest(tags=["dog", "cat"]))
    assert not matches_search_filters(tagged, TextSearchRequest(tags=["city"]))


def test_imported_after_compares_instants_across_timezone_offsets() -> None:
    stored = stored_image(
        "offset",
        "image/jpeg",
        1000,
        800,
        1_000_000,
        "2026-07-01T00:30:00+01:00",
    )

    assert not matches_search_filters(
        stored,
        TextSearchRequest(imported_after="2026-06-30T23:45:00+00:00"),
    )


def test_imported_after_rejects_invalid_and_naive_timestamps() -> None:
    with pytest.raises(ValidationError):
        TextSearchRequest(imported_after="not-a-date")
    with pytest.raises(ValidationError):
        TextSearchRequest(imported_after="2026-07-01T00:00:00")


def test_filtered_text_search_expands_beyond_initial_top_100() -> None:
    hits = []
    records = {}
    for position in range(101):
        image = IndexedImage(str(position), f"{position}.jpg", "image/jpeg")
        hits.append(SearchHit(image, 1.0 - position * 0.001))
        tags = (ImageTag("target", "目标", 0.9),) if position == 100 else ()
        records[image.image_id] = StoredImage(
            image=image,
            stored_filename=image.filename,
            sha256=image.image_id,
            size_bytes=1,
            model_id="test",
            width=10,
            height=10,
            created_at="2026-07-01T00:00:00+00:00",
            tags=tags,
        )

    class RankedIndex:
        def __len__(self):
            return len(hits)

        def search(self, query, top_k):
            return hits[:top_k]

    class Repository:
        def find_by_id(self, image_id):
            return records.get(image_id)

    class Encoder:
        def encode_texts(self, texts):
            return np.asarray([[1.0]], dtype=np.float32)

    state = SimpleNamespace(
        index=RankedIndex(),
        library=SimpleNamespace(repository=Repository()),
        encoder=Encoder(),
        reranker=None,
        mode="local",
    )
    request = SimpleNamespace(app=SimpleNamespace(state=state))

    results = search_by_text(
        TextSearchRequest(query="anything", tags=["target"], top_k=12),
        request,
    )

    assert [result.image_id for result in results] == ["100"]
