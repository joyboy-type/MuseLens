from scripts.evaluate_precision_reranker import threshold_metrics


def test_threshold_metrics_balance_hits_and_rejections() -> None:
    outcomes = [
        {
            "kind": "positive",
            "expected_category": "dog",
            "candidates": [
                {"score": 0.8, "categories": ["dog"]},
                {"score": 0.2, "categories": ["cat"]},
            ],
        },
        {
            "kind": "negative",
            "candidates": [{"score": 0.3, "categories": ["bus"]}],
        },
    ]
    metrics = threshold_metrics(outcomes, 0.5)
    assert metrics["positive_hit_at_1"] == 1
    assert metrics["positive_hit_at_5"] == 1
    assert metrics["negative_rejection_rate"] == 1
