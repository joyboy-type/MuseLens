from muselens.demo_evaluation import (
    evaluate_negative_query,
    evaluate_positive_query,
    summarize_outcomes,
)


def test_demo_query_outcomes_and_summary() -> None:
    categories = {
        "dog.jpg": {"dog", "bed"},
        "car.jpg": {"car"},
    }
    positive = [
        evaluate_positive_query(
            {"query": "dog", "language": "en", "expected_category": "dog"},
            [
                {"filename": "dog.jpg", "score": 0.8},
                {"filename": "car.jpg", "score": 0.4},
            ],
            categories,
        ),
        evaluate_positive_query(
            {"query": "汽车", "language": "zh", "expected_category": "car"},
            [{"filename": "dog.jpg", "score": 0.7}],
            categories,
        ),
    ]
    negative = [
        evaluate_negative_query(
            {"query": "train", "language": "en", "absent_category": "train"},
            [],
        )
    ]

    summary = summarize_outcomes(positive, negative)

    assert positive[0].hit_at_1 is True
    assert positive[1].hit_at_5 is False
    assert negative[0].hit_at_1 is True
    assert summary["hit_at_1"] == 0.5
    assert summary["hit_at_5"] == 0.5
    assert summary["negative_rejection_rate"] == 1.0
    assert summary["language_metrics"]["en"]["hit_at_1"] == 1.0
    assert summary["language_metrics"]["zh"]["hit_at_1"] == 0.0
