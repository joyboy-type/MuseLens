from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class RejectionPolicy:
    absolute_floor: float
    minimum_z_score: float = 0.0


def top_score_z_scores(similarities: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    scores = np.asarray(similarities, dtype=np.float32)
    if scores.ndim != 2 or scores.shape[1] < 2:
        raise ValueError("similarities must contain at least two candidates per query")
    top_scores = np.max(scores, axis=1)
    standard_deviation = np.std(scores, axis=1)
    z_scores = (top_scores - np.mean(scores, axis=1)) / np.maximum(
        standard_deviation,
        1e-8,
    )
    return top_scores, z_scores


def accepted_queries(
    similarities: np.ndarray,
    policy: RejectionPolicy,
) -> np.ndarray:
    top_scores, z_scores = top_score_z_scores(similarities)
    return (top_scores >= policy.absolute_floor) & (
        z_scores >= policy.minimum_z_score
    )


def rejection_metrics(
    positive_similarities: np.ndarray,
    relevant_candidate: np.ndarray,
    negative_similarities: np.ndarray,
    policy: RejectionPolicy,
    top_k: int = 5,
) -> dict[str, float]:
    positive = np.asarray(positive_similarities)
    negative = np.asarray(negative_similarities)
    relevant = np.asarray(relevant_candidate)
    if positive.ndim != 2 or negative.ndim != 2:
        raise ValueError("positive and negative similarities must be matrices")
    if positive.shape[1] != negative.shape[1]:
        raise ValueError("positive and negative queries must share the candidate set")
    if relevant.shape != (positive.shape[0],):
        raise ValueError("relevant_candidate must contain one index per positive query")
    if not 1 <= top_k <= positive.shape[1]:
        raise ValueError("top_k is outside the candidate set")

    rankings = np.argsort(-positive, axis=1)[:, :top_k]
    retrieved = np.any(rankings == relevant[:, None], axis=1)
    positive_accepted = accepted_queries(positive, policy)
    negative_accepted = accepted_queries(negative, policy)
    retrieval_after_rejection = float(np.mean(retrieved & positive_accepted))
    negative_rejection_rate = float(np.mean(~negative_accepted))
    return {
        "positive_accept_rate": float(np.mean(positive_accepted)),
        f"recall_at_{top_k}_after_rejection": retrieval_after_rejection,
        "negative_rejection_rate": negative_rejection_rate,
        "balanced_score": (retrieval_after_rejection + negative_rejection_rate) / 2,
    }


def calibrate_rejection_policy(
    positive_similarities: np.ndarray,
    relevant_candidate: np.ndarray,
    negative_similarities: np.ndarray,
    absolute_floors: Iterable[float],
    minimum_z_scores: Iterable[float] = (0.0,),
    top_k: int = 5,
) -> tuple[RejectionPolicy, dict[str, float]]:
    candidates = []
    for floor in absolute_floors:
        for minimum_z_score in minimum_z_scores:
            policy = RejectionPolicy(float(floor), float(minimum_z_score))
            metrics = rejection_metrics(
                positive_similarities,
                relevant_candidate,
                negative_similarities,
                policy,
                top_k,
            )
            candidates.append((policy, metrics))
    if not candidates:
        raise ValueError("at least one policy candidate is required")
    return max(
        candidates,
        key=lambda item: (
            item[1]["balanced_score"],
            item[1][f"recall_at_{top_k}_after_rejection"],
            item[1]["negative_rejection_rate"],
            -item[0].absolute_floor,
            -item[0].minimum_z_score,
        ),
    )


def retrieval_metrics(
    similarities: np.ndarray,
    relevant_candidate: np.ndarray,
    recall_at: Iterable[int] = (1, 5, 10),
) -> dict[str, float]:
    """Evaluate one-relevant-item retrieval from a query-candidate similarity matrix."""
    scores = np.asarray(similarities)
    relevant = np.asarray(relevant_candidate)
    if scores.ndim != 2:
        raise ValueError("similarities must be a two-dimensional matrix")
    if relevant.shape != (scores.shape[0],):
        raise ValueError("relevant_candidate must contain one index per query")
    if np.any(relevant < 0) or np.any(relevant >= scores.shape[1]):
        raise ValueError("relevant candidate index is out of range")

    ranked_candidates = np.argsort(-scores, axis=1)
    matches = ranked_candidates == relevant[:, None]
    ranks = np.argmax(matches, axis=1) + 1
    metrics = {
        f"recall_at_{k}": float(np.mean(ranks <= k))
        for k in recall_at
        if 1 <= k <= scores.shape[1]
    }
    metrics["mrr"] = float(np.mean(1.0 / ranks))
    metrics["mean_rank"] = float(np.mean(ranks))
    metrics["median_rank"] = float(np.median(ranks))
    return metrics
