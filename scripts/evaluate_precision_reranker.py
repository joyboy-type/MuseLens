#!/usr/bin/env python3
"""Evaluate two-stage SigLIP recall plus Qwen3-VL precision reranking."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from muselens.demo_evaluation import search_text_api, threshold_metrics
from muselens.reranker import QwenVLReranker


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url")
    parser.add_argument("--model", default="Qwen/Qwen3-VL-Reranker-2B")
    parser.add_argument("--template", default="A photo of {query}.")
    parser.add_argument(
        "--suite",
        type=Path,
        default=PROJECT_ROOT / "demo_assets" / "query_suite.json",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=PROJECT_ROOT / "demo_assets" / "manifest.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "artifacts/evaluations/demo-qwen-reranker-v1.json",
    )
    parser.add_argument("--timeout", type=float, default=120)
    return parser.parse_args()


def write_artifact(
    path: Path,
    args: argparse.Namespace,
    suite: dict[str, Any],
    outcomes: list[dict[str, Any]],
) -> None:
    thresholds = [round(value / 20, 2) for value in range(1, 20)]
    artifact = {
        "suite": suite["name"],
        "suite_version": suite["version"],
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "recall_template": args.template,
        "reranker_model": args.model,
        "completed_queries": len(outcomes),
        "threshold_metrics": [threshold_metrics(outcomes, value) for value in thresholds]
        if outcomes and any(item["kind"] == "positive" for item in outcomes)
        and any(item["kind"] == "negative" for item in outcomes)
        else [],
        "outcomes": outcomes,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n")


def main() -> None:
    args = parse_args()
    suite = json.loads(args.suite.read_text())
    manifest = json.loads(args.manifest.read_text())
    records = {record["image_id"]: record for record in manifest["images"]}
    specifications = [
        {**item, "kind": "positive"} for item in suite["positive_queries"]
    ] + [{**item, "kind": "negative"} for item in suite["negative_queries"]]
    reranker = QwenVLReranker(args.model)
    outcomes: list[dict[str, Any]] = []

    for index, specification in enumerate(specifications, start=1):
        query = specification["query"]
        recalled = search_text_api(
            args.base_url,
            args.template.format(query=query),
            args.timeout,
        )
        available = [(item, records.get(item["image_id"])) for item in recalled]
        available = [(item, record) for item, record in available if record is not None]
        paths = [
            PROJECT_ROOT / "demo_assets" / "images" / record["stored_filename"]
            for _, record in available
        ]
        print(
            f"[{index:02d}/{len(specifications):02d}] {query} "
            f"candidates={len(paths)}",
            flush=True,
        )
        scores = reranker.score(query, paths)
        candidates = sorted(
            [
                {
                    "image_id": item["image_id"],
                    "original_filename": record["original_filename"],
                    "categories": record["categories"],
                    "recall_score": item["score"],
                    "score": score,
                }
                for (item, record), score in zip(available, scores, strict=True)
            ],
            key=lambda candidate: candidate["score"],
            reverse=True,
        )
        outcomes.append(
            {
                "kind": specification["kind"],
                "query": query,
                "language": specification["language"],
                "expected_category": specification.get("expected_category"),
                "absent_category": specification.get("absent_category"),
                "candidates": candidates,
            }
        )
        write_artifact(args.output, args, suite, outcomes)

    artifact = json.loads(args.output.read_text())
    print(json.dumps(artifact["threshold_metrics"], ensure_ascii=False, indent=2))
    print(f"artifact={args.output}")


if __name__ == "__main__":
    main()
