#!/usr/bin/env python3
"""Verify a deployed MuseLens instance with a bilingual retrieval contract."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from muselens.deployment import (
    validate_deployment_contract,
    validate_deployment_health,
)
from muselens.demo_evaluation import (
    QueryOutcome,
    evaluate_positive_query,
    search_text_api,
    summarize_outcomes,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test a public MuseLens deployment.")
    parser.add_argument("base_url")
    parser.add_argument("--timeout", type=float, default=180)
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
        "--contract",
        choices=("quick", "full"),
        default="quick",
        help="Quick tests representative bilingual categories; full runs every positive query.",
    )
    parser.add_argument("--min-hit-at-5", type=float, default=0.9)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def request_json(
    base_url: str,
    path: str,
    *,
    timeout: float,
    payload: dict[str, Any] | None = None,
) -> Any:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    request = Request(
        urljoin(base_url.rstrip("/") + "/", path.lstrip("/")),
        data=data,
        headers=headers,
        method="POST" if payload is not None else "GET",
    )
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - caller URL
        return json.load(response)


def validate_write_guard(base_url: str, timeout: float) -> None:
    """Prove the fixed public corpus rejects writes before reading the uploaded body."""
    boundary = "muselens-deployment-guard"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="guard.txt"\r\n'
        "Content-Type: text/plain\r\n\r\n"
        "guard\r\n"
        f"--{boundary}--\r\n"
    ).encode()
    request = Request(
        urljoin(base_url.rstrip("/") + "/", "v1/images"),
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout):  # noqa: S310 - caller URL
            pass
    except HTTPError as error:
        if error.code == 403:
            return
        raise ValueError(f"Fixed-library write returned HTTP {error.code}, expected 403") from error
    raise ValueError("Fixed-library write unexpectedly succeeded")


def representative_queries(specifications: list[dict[str, str]]) -> list[dict[str, str]]:
    """Select one English and Chinese query across four distinct categories."""
    categories: list[str] = []
    for specification in specifications:
        category = specification["expected_category"]
        if category not in categories:
            categories.append(category)
        if len(categories) == 4:
            break
    return [
        specification
        for category in categories
        for language in ("en", "zh")
        if (
            specification := next(
                item
                for item in specifications
                if item["expected_category"] == category and item["language"] == language
            )
        )
    ]


def evaluate_contract(
    base_url: str,
    specifications: list[dict[str, str]],
    categories_by_filename: dict[str, set[str]],
    timeout: float,
) -> list[QueryOutcome]:
    outcomes = []
    for index, specification in enumerate(specifications, start=1):
        query = specification["query"]
        print(f"[{index:02d}/{len(specifications):02d}] query={query!r}", flush=True)
        results = search_text_api(base_url, query, timeout)
        outcomes.append(
            evaluate_positive_query(specification, results, categories_by_filename)
        )
    return outcomes


def main() -> None:
    args = parse_args()
    started = perf_counter()
    try:
        health = request_json(args.base_url, "/health", timeout=args.timeout)
        validate_deployment_health(health)
        validate_write_guard(args.base_url, args.timeout)
        suite = json.loads(args.suite.read_text())
        manifest = json.loads(args.manifest.read_text())
        categories_by_filename = {
            record["original_filename"]: set(record["categories"])
            for record in manifest["images"]
        }
        specifications = suite["positive_queries"]
        if args.contract == "quick":
            specifications = representative_queries(specifications)
        outcomes = evaluate_contract(
            args.base_url,
            specifications,
            categories_by_filename,
            args.timeout,
        )
        summary = summarize_outcomes(outcomes, [])
        validate_deployment_contract(summary, min_hit_at_5=args.min_hit_at_5)
    except (HTTPError, URLError, TimeoutError, ValueError, OSError, KeyError) as error:
        raise SystemExit(f"Deployment smoke test failed: {error}") from error

    elapsed = perf_counter() - started
    artifact = {
        "suite": suite["name"],
        "suite_version": suite["version"],
        "contract": args.contract,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "summary": summary,
        "outcomes": [asdict(outcome) for outcome in outcomes],
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n")
    print("deployment_ok=true")
    print(f"mode={health['mode']}")
    print(f"indexed_images={health['indexed_images']}")
    print("fixed_library_write_guard=403")
    print(f"contract={args.contract}")
    print(f"queries={summary['positive_queries']}")
    print(f"hit_at_5={summary['hit_at_5']:.4f}")
    print(f"elapsed_seconds={elapsed:.2f}")


if __name__ == "__main__":
    main()
