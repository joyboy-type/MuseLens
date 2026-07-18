import pytest

from muselens.deployment import validate_deployment_health, validate_deployment_search


def test_validate_health_accepts_read_only_demo() -> None:
    validate_deployment_health(
        {
            "status": "ok",
            "mode": "demo",
            "library_writable": False,
            "temporary_galleries_enabled": True,
            "indexed_images": 24,
        }
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "degraded"),
        ("mode", "local"),
        ("library_writable", True),
        ("temporary_galleries_enabled", False),
        ("indexed_images", 0),
    ],
)
def test_validate_health_rejects_unsafe_or_empty_deployment(field, value) -> None:
    health = {
        "status": "ok",
        "mode": "demo",
        "library_writable": False,
        "temporary_galleries_enabled": True,
        "indexed_images": 24,
    }
    health[field] = value

    with pytest.raises(ValueError):
        validate_deployment_health(health)


def test_validate_search_requires_results_and_contract_fields() -> None:
    validate_deployment_search(
        [
            {
                "image_id": "image-1",
                "filename": "dog.jpg",
                "content_type": "image/jpeg",
                "score": 0.42,
            }
        ]
    )

    with pytest.raises(ValueError, match="no results"):
        validate_deployment_search([])
    with pytest.raises(ValueError, match="missing fields"):
        validate_deployment_search([{"image_id": "image-1"}])
