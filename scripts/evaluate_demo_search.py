#!/usr/bin/env python3
"""Evaluate the public demo through its real HTTP search API."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from muselens.demo_evaluation import (
    QueryOutcome,
    evaluate_negative_query,
    evaluate_positive_query,
    summarize_outcomes,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the MuseLens public demo API.")
    parser.add_argument("base_url")
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
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument(
        "--template",
        default="{query}",
        help="Text sent to the API; must contain the {query} placeholder.",
    )
    return parser.parse_args()


def search(base_url: str, query: str, timeout: float) -> list[dict[str, Any]]:
    payload = json.dumps({"query": query, "top_k": 5}).encode()
    request = Request(
        urljoin(base_url.rstrip("/") + "/", "v1/search/text"),
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - caller URL
        return json.load(response)


def print_failures(label: str, outcomes: list[QueryOutcome]) -> None:
    failed = [outcome for outcome in outcomes if not outcome.hit_at_5]
    print(f"{label}_failures={len(failed)}")
    for outcome in failed:
        print(
            f"  query={outcome.query!r} expected={outcome.expected_category!r} "
            f"returned={outcome.returned} top={outcome.top_filename!r} "
            f"score={outcome.top_score!r}"
        )


def run_queries(
    base_url: str,
    specifications: list[dict[str, Any]],
    timeout: float,
    evaluator: Any,
    *evaluator_args: Any,
    template: str = "{query}",
) -> list[QueryOutcome]:
    outcomes = []
    total = len(specifications)
    for index, specification in enumerate(specifications, start=1):
        query = specification["query"]
        print(f"[{index:02d}/{total:02d}] {query}", flush=True)
        outcomes.append(
            evaluator(
                specification,
                search(base_url, template.format(query=query), timeout),
                *evaluator_args,
            )
        )
    return outcomes


def main() -> None:
    args = parse_args()
    suite = json.loads(args.suite.read_text())
    manifest = json.loads(args.manifest.read_text())
    categories_by_filename = {
        record["original_filename"]: set(record["categories"])
        for record in manifest["images"]
    }

    print("Evaluating positive queries", flush=True)
    positive = run_queries(
        args.base_url,
        suite["positive_queries"],
        args.timeout,
        evaluate_positive_query,
        categories_by_filename,
        template=args.template,
    )
    print("Evaluating absent-content queries", flush=True)
    negative = run_queries(
        args.base_url,
        suite["negative_queries"],
        args.timeout,
        evaluate_negative_query,
        template=args.template,
    )
    summary = summarize_outcomes(positive, negative)
    artifact = {
        "suite": suite["name"],
        "suite_version": suite["version"],
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "query_template": args.template,
        "summary": summary,
        "positive_outcomes": [asdict(outcome) for outcome in positive],
        "negative_outcomes": [asdict(outcome) for outcome in negative],
    }

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print_failures("positive", positive)
    print_failures("negative", negative)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n")
        print(f"artifact={args.output}")


if __name__ == "__main__":
    main()
