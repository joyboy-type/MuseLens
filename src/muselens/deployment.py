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


def validate_deployment_contract(
    summary: dict[str, Any],
    *,
    min_hit_at_5: float = 0.9,
) -> None:
    """Fail a deployment when its bilingual retrieval contract regresses."""
    positive_queries = int(summary.get("positive_queries", 0))
    if positive_queries < 2:
        raise ValueError("Deployment contract must contain multiple positive queries")
    hit_at_5 = float(summary.get("hit_at_5", 0.0))
    if hit_at_5 < min_hit_at_5:
        raise ValueError(
            f"Deployment Hit@5 {hit_at_5:.2%} is below the required {min_hit_at_5:.2%}"
        )
    language_metrics = summary.get("language_metrics", {})
    missing_languages = {"en", "zh"} - set(language_metrics)
    if missing_languages:
        raise ValueError(
            f"Deployment contract is missing languages: {sorted(missing_languages)}"
        )
