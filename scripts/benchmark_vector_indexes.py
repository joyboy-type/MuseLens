#!/usr/bin/env python3
"""Compare exact vector-index implementations without model or HTTP overhead."""

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.metadata import version
import json
from pathlib import Path
import platform
from statistics import mean
import sys
from time import perf_counter
from typing import Any

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from muselens.index import (  # noqa: E402
    IndexedImage,
    SearchHit,
    create_vector_index,
    normalize,
)
from muselens.repository import ImageRepository  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark exact MuseLens vector indexes.")
    parser.add_argument(
        "--database",
        type=Path,
        default=PROJECT_ROOT / "data" / "benchmarks" / "coco-live" / "state" / "index.sqlite3",
    )
    parser.add_argument("--model-id", default="google/siglip2-base-patch16-224")
    parser.add_argument("--queries", type=int, default=1000)
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT
        / "artifacts"
        / "evaluations"
        / "vector-index-5k-v1.json",
    )
    return parser.parse_args()


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = min(round((len(ordered) - 1) * fraction), len(ordered) - 1)
    return ordered[position]


@dataclass
class LegacyLoopIndex:
    """The pre-optimization implementation retained only for a fair benchmark."""

    def __post_init__(self) -> None:
        self.vectors: dict[str, np.ndarray] = {}
        self.images: dict[str, IndexedImage] = {}

    def add(self, image: IndexedImage, vector: np.ndarray) -> None:
        self.images[image.image_id] = image
        self.vectors[image.image_id] = normalize(vector)

    def search(self, query: np.ndarray, top_k: int) -> list[SearchHit]:
        normalized_query = normalize(query)
        scored = [
            SearchHit(self.images[image_id], float(vector @ normalized_query))
            for image_id, vector in self.vectors.items()
        ]
        return sorted(scored, key=lambda hit: hit.score, reverse=True)[:top_k]


def create_backend(name: str) -> Any:
    if name == "legacy-loop":
        return LegacyLoopIndex()
    if name == "faiss":
        import faiss

        faiss.omp_set_num_threads(1)
    return create_vector_index(name)


def run_backend(
    name: str,
    entries: list[tuple[Any, np.ndarray]],
    queries: list[np.ndarray],
    top_k: int,
    trials: int,
) -> tuple[dict[str, Any], list[list[SearchHit]]]:
    index = create_backend(name)
    build_started = perf_counter()
    for stored, vector in entries:
        index.add(stored.image, vector)
    add_seconds = perf_counter() - build_started

    first_started = perf_counter()
    index.search(queries[0], top_k)
    first_search_ms = (perf_counter() - first_started) * 1000
    for query in queries[:20]:
        index.search(query, top_k)

    latencies = []
    rankings = []
    trial_mean_latency_ms = []
    total_seconds = 0.0
    for trial in range(trials):
        trial_latencies = []
        benchmark_started = perf_counter()
        for query in queries:
            query_started = perf_counter()
            hits = index.search(query, top_k)
            trial_latencies.append((perf_counter() - query_started) * 1000)
            if trial == 0:
                rankings.append(hits)
        trial_seconds = perf_counter() - benchmark_started
        total_seconds += trial_seconds
        latencies.extend(trial_latencies)
        trial_mean_latency_ms.append(mean(trial_latencies))
    result = {
        "backend": name,
        "add_seconds": add_seconds,
        "first_search_build_ms": first_search_ms,
        "queries_per_trial": len(queries),
        "trials": trials,
        "measured_queries": len(queries) * trials,
        "total_seconds": total_seconds,
        "queries_per_second": len(queries) * trials / total_seconds,
        "mean_latency_ms": mean(latencies),
        "p50_latency_ms": percentile(latencies, 0.50),
        "p95_latency_ms": percentile(latencies, 0.95),
        "p99_latency_ms": percentile(latencies, 0.99),
        "trial_mean_latency_ms": trial_mean_latency_ms,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return result, rankings


def agreement(
    reference: list[list[SearchHit]],
    candidate: list[list[SearchHit]],
) -> dict[str, Any]:
    exact_rankings = 0
    max_score_difference = 0.0
    for expected, actual in zip(reference, candidate, strict=True):
        expected_ids = [hit.image.image_id for hit in expected]
        actual_ids = [hit.image.image_id for hit in actual]
        exact_rankings += int(expected_ids == actual_ids)
        actual_scores = {hit.image.image_id: hit.score for hit in actual}
        for hit in expected:
            if hit.image.image_id in actual_scores:
                max_score_difference = max(
                    max_score_difference,
                    abs(hit.score - actual_scores[hit.image.image_id]),
                )
    return {
        "exact_ranking_queries": exact_rankings,
        "queries": len(reference),
        "exact_ranking_rate": exact_rankings / len(reference),
        "max_common_score_difference": max_score_difference,
    }


def main() -> None:
    args = parse_args()
    repository = ImageRepository(args.database)
    entries = repository.load_index(model_id=args.model_id)
    if not entries:
        raise RuntimeError(f"No vectors found in {args.database} for {args.model_id}")
    if args.queries < 1 or args.queries > len(entries):
        raise ValueError(f"--queries must be between 1 and {len(entries)}")
    if args.trials < 1:
        raise ValueError("--trials must be at least 1")
    if args.top_k < 1 or args.top_k > len(entries):
        raise ValueError(f"--top-k must be between 1 and {len(entries)}")
    queries = [vector for _, vector in entries[: args.queries]]

    result: dict[str, Any] = {
        "experiment": "exact-vector-index-comparison",
        "run_at": datetime.now(timezone.utc).isoformat(),
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "numpy": np.__version__,
            "faiss_cpu": version("faiss-cpu"),
        },
        "database": str(args.database.resolve().relative_to(PROJECT_ROOT)),
        "model_id": args.model_id,
        "images": len(entries),
        "embedding_dimension": int(entries[0][1].size),
        "top_k": args.top_k,
        "backends": [],
    }

    rankings_by_backend = {}
    for backend in ("legacy-loop", "numpy", "faiss"):
        backend_result, rankings = run_backend(
            backend,
            entries,
            queries,
            args.top_k,
            args.trials,
        )
        result["backends"].append(backend_result)
        rankings_by_backend[backend] = rankings

    reference = rankings_by_backend["numpy"]
    result["agreement_with_numpy"] = {
        backend: agreement(reference, rankings)
        for backend, rankings in rankings_by_backend.items()
        if backend != "numpy"
    }
    by_name = {item["backend"]: item for item in result["backends"]}
    result["speedup_over_legacy_mean"] = {
        backend: by_name["legacy-loop"]["mean_latency_ms"]
        / by_name[backend]["mean_latency_ms"]
        for backend in ("numpy", "faiss")
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result["agreement_with_numpy"], ensure_ascii=False, indent=2))
    print(f"saved={args.output}")


if __name__ == "__main__":
    main()
