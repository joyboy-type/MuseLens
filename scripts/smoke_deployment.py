#!/usr/bin/env python3
"""Verify a deployed MuseLens instance without mutating its image library."""

from __future__ import annotations

import argparse
import json
from time import perf_counter
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from muselens.deployment import (
    validate_deployment_health,
    validate_deployment_search,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test a public MuseLens deployment.")
    parser.add_argument("base_url")
    parser.add_argument("--query", default="dog")
    parser.add_argument("--timeout", type=float, default=180)
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


def main() -> None:
    args = parse_args()
    started = perf_counter()
    try:
        health = request_json(args.base_url, "/health", timeout=args.timeout)
        validate_deployment_health(health)
        results = request_json(
            args.base_url,
            "/v1/search/text",
            timeout=args.timeout,
            payload={"query": args.query, "top_k": 5},
        )
        validate_deployment_search(results)
    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        raise SystemExit(f"Deployment smoke test failed: {error}") from error

    elapsed = perf_counter() - started
    print("deployment_ok=true")
    print(f"mode={health['mode']}")
    print(f"indexed_images={health['indexed_images']}")
    print(f"query={args.query}")
    print(f"results={len(results)}")
    print(f"elapsed_seconds={elapsed:.2f}")


if __name__ == "__main__":
    main()
