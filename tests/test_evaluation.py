import numpy as np
import pytest

from muselens.evaluation import (
    RejectionPolicy,
    calibrate_rejection_policy,
    rejection_metrics,
    retrieval_metrics,
)


def test_retrieval_metrics_for_known_ranking() -> None:
    similarities = np.array(
        [
            [0.9, 0.2, 0.1],
            [0.8, 0.7, 0.1],
            [0.9, 0.8, 0.7],
        ]
    )
    metrics = retrieval_metrics(similarities, np.array([0, 1, 2]), recall_at=(1, 2, 3))

    assert metrics["recall_at_1"] == pytest.approx(1 / 3)
    assert metrics["recall_at_2"] == pytest.approx(2 / 3)
    assert metrics["recall_at_3"] == 1.0
    assert metrics["mrr"] == pytest.approx((1 + 1 / 2 + 1 / 3) / 3)


def test_retrieval_metrics_validates_query_count() -> None:
    with pytest.raises(ValueError, match="one index per query"):
        retrieval_metrics(np.ones((2, 3)), np.array([0]))


def test_rejection_metrics_balance_retrieval_and_negative_rejection() -> None:
    positive = np.array([[0.8, 0.2, 0.1], [0.25, 0.2, 0.1]])
    negative = np.array([[0.24, 0.2, 0.1], [0.15, 0.14, 0.13]])
    metrics = rejection_metrics(
        positive,
        np.array([0, 0]),
        negative,
        RejectionPolicy(absolute_floor=0.3),
        top_k=1,
    )

    assert metrics["positive_accept_rate"] == 0.5
    assert metrics["recall_at_1_after_rejection"] == 0.5
    assert metrics["negative_rejection_rate"] == 1.0
    assert metrics["balanced_score"] == 0.75


def test_policy_calibration_selects_the_best_floor() -> None:
    positive = np.array([[0.8, 0.2], [0.7, 0.1]])
    negative = np.array([[0.4, 0.2], [0.3, 0.1]])

    policy, metrics = calibrate_rejection_policy(
        positive,
        np.array([0, 0]),
        negative,
        absolute_floors=(0.25, 0.5, 0.9),
        top_k=1,
    )

    assert policy.absolute_floor == 0.5
    assert metrics["balanced_score"] == 1.0
