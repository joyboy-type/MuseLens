from muselens.api import matches_search_filters, sort_filtered_results
from muselens.index import IndexedImage
from muselens.repository import StoredImage
from muselens.schemas import TextSearchRequest


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
        stored_image(
            "portrait", "image/jpeg", 1200, 2400, 2_000_000, "2026-07-10T00:00:00+00:00"
        ),
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
