from typing import Any


def validate_deployment_health(health: dict[str, Any]) -> None:
    if health.get("status") != "ok":
        raise ValueError(f"Unexpected health status: {health.get('status')!r}")
    if health.get("mode") != "demo":
        raise ValueError(f"Public service must use demo mode, got {health.get('mode')!r}")
    if health.get("library_writable") is not False:
        raise ValueError("Public fixed library is unexpectedly writable")
    if health.get("temporary_galleries_enabled") is not True:
        raise ValueError("Temporary visitor galleries are unexpectedly disabled")
    if int(health.get("indexed_images", 0)) < 1:
        raise ValueError("Public demo corpus is empty")


def validate_deployment_search(results: list[dict[str, Any]]) -> None:
    if not results:
        raise ValueError("Smoke query returned no results")
    required = {"image_id", "filename", "content_type", "score"}
    missing = required - results[0].keys()
    if missing:
        raise ValueError(f"Search result is missing fields: {sorted(missing)}")
