from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class QueryOutcome:
    query: str
    language: str
    expected_category: str | None
    returned: int
    hit_at_1: bool
    hit_at_5: bool
    top_filename: str | None
    top_score: float | None


def evaluate_positive_query(
    specification: dict[str, str],
    results: list[dict[str, Any]],
    categories_by_filename: dict[str, set[str]],
) -> QueryOutcome:
    expected = specification["expected_category"]
    categories = [categories_by_filename.get(result["filename"], set()) for result in results]
    return QueryOutcome(
        query=specification["query"],
        language=specification["language"],
        expected_category=expected,
        returned=len(results),
        hit_at_1=bool(categories and expected in categories[0]),
        hit_at_5=any(expected in item for item in categories[:5]),
        top_filename=results[0]["filename"] if results else None,
        top_score=results[0].get("score") if results else None,
    )


def evaluate_negative_query(
    specification: dict[str, str],
    results: list[dict[str, Any]],
) -> QueryOutcome:
    return QueryOutcome(
        query=specification["query"],
        language=specification["language"],
        expected_category=None,
        returned=len(results),
        hit_at_1=not results,
        hit_at_5=not results,
        top_filename=results[0]["filename"] if results else None,
        top_score=results[0].get("score") if results else None,
    )


def summarize_outcomes(
    positive: list[QueryOutcome],
    negative: list[QueryOutcome],
) -> dict[str, Any]:
    def rate(values: list[bool]) -> float:
        return sum(values) / len(values) if values else 0.0

    languages = sorted({outcome.language for outcome in positive})
    language_metrics = {
        language: {
            "queries": len(items),
            "hit_at_1": rate([item.hit_at_1 for item in items]),
            "hit_at_5": rate([item.hit_at_5 for item in items]),
        }
        for language in languages
        if (items := [item for item in positive if item.language == language])
    }
    return {
        "positive_queries": len(positive),
        "hit_at_1": rate([item.hit_at_1 for item in positive]),
        "hit_at_5": rate([item.hit_at_5 for item in positive]),
        "empty_positive_rate": rate([item.returned == 0 for item in positive]),
        "negative_queries": len(negative),
        "negative_rejection_rate": rate([item.returned == 0 for item in negative]),
        "language_metrics": language_metrics,
    }
