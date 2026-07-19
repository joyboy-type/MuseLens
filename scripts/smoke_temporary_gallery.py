#!/usr/bin/env python3
"""Verify the complete temporary-gallery workflow on a public deployment."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from time import monotonic, sleep
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from muselens.deployment_smoke import multipart_files, select_upload_assets


PROJECT_ROOT = Path(__file__).resolve().parents[1]
QUERIES = {
    "dog": ("dog", "狗"),
    "car": ("car", "汽车"),
    "pizza": ("pizza", "披萨"),
}


def request(
    base_url: str,
    path: str,
    *,
    timeout: float,
    method: str = "GET",
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
):
    target = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    outbound_headers = {"Accept": "application/json", **(headers or {})}
    return urlopen(  # noqa: S310 - caller controls the deployment URL
        Request(target, data=data, headers=outbound_headers, method=method),
        timeout=timeout,
    )


def request_json(
    base_url: str,
    path: str,
    *,
    timeout: float,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> Any:
    data = None
    headers = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers = {"Content-Type": "application/json"}
    with request(
        base_url,
        path,
        timeout=timeout,
        method=method,
        data=data,
        headers=headers,
    ) as response:
        return json.load(response)


def wait_for_gallery(
    base_url: str,
    session_id: str,
    *,
    timeout: float,
) -> dict[str, Any]:
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        snapshot = request_json(
            base_url,
            f"/v1/demo/sessions/{session_id}",
            timeout=min(timeout, 30),
        )
        if snapshot["status"] in {"completed", "partial", "failed"}:
            return snapshot
        sleep(1)
    raise TimeoutError("Temporary gallery indexing did not finish before timeout.")


def expect_http(base_url: str, path: str, expected: int, timeout: float) -> None:
    try:
        with request(base_url, path, timeout=timeout):
            status = 200
    except HTTPError as error:
        status = error.code
    if status != expected:
        raise ValueError(f"{path} returned HTTP {status}, expected {expected}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Smoke-test temporary upload, indexing, retrieval, isolation, and cleanup."
    )
    parser.add_argument("base_url")
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=PROJECT_ROOT / "demo_assets" / "manifest.json",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    assets = select_upload_assets(args.manifest)
    body, content_type = multipart_files(assets)
    session_id: str | None = None
    query_results = []
    cleanup_confirmed = False
    try:
        with request(
            args.base_url,
            "/v1/demo/sessions",
            timeout=args.timeout,
            method="POST",
            data=body,
            headers={"Content-Type": content_type},
        ) as response:
            if response.status != 202:
                raise ValueError(f"Gallery creation returned HTTP {response.status}")
            created = json.load(response)
        session_id = created["session_id"]
        snapshot = wait_for_gallery(
            args.base_url,
            session_id,
            timeout=args.timeout,
        )
        if snapshot["status"] != "completed" or snapshot["imported_files"] != len(assets):
            raise ValueError(f"Temporary gallery indexing failed: {snapshot}")

        images = request_json(
            args.base_url,
            f"/v1/demo/sessions/{session_id}/images",
            timeout=args.timeout,
        )
        if {image["filename"] for image in images} != {
            asset.upload_name for asset in assets
        }:
            raise ValueError("Temporary gallery image listing does not match uploads.")

        first_image_id = images[0]["image_id"]
        with request(
            args.base_url,
            f"/v1/demo/sessions/{session_id}/images/{first_image_id}/content",
            timeout=args.timeout,
        ) as response:
            if response.headers.get("Cache-Control") != "private, no-store":
                raise ValueError("Temporary image content is missing private cache protection.")

        for asset in assets:
            for query in QUERIES[asset.category]:
                hits = request_json(
                    args.base_url,
                    f"/v1/demo/sessions/{session_id}/search/text",
                    timeout=args.timeout,
                    method="POST",
                    payload={"query": query, "top_k": len(assets)},
                )
                top_filename = hits[0]["filename"] if hits else None
                query_results.append(
                    {"query": query, "expected": asset.upload_name, "top": top_filename}
                )
                if top_filename != asset.upload_name:
                    raise ValueError(
                        f"Query {query!r} returned {top_filename!r}, expected {asset.upload_name!r}."
                    )

        expect_http(
            args.base_url,
            "/v1/demo/sessions/not-this-session/images",
            404,
            args.timeout,
        )
    finally:
        if session_id is not None:
            with request(
                args.base_url,
                f"/v1/demo/sessions/{session_id}",
                timeout=args.timeout,
                method="DELETE",
            ) as response:
                if response.status != 204:
                    raise ValueError(f"Gallery cleanup returned HTTP {response.status}")
            expect_http(
                args.base_url,
                f"/v1/demo/sessions/{session_id}",
                404,
                args.timeout,
            )
            cleanup_confirmed = True

    report = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "uploaded_files": len(assets),
        "queries": query_results,
        "session_isolation": True,
        "private_cache_control": True,
        "cleanup_confirmed": cleanup_confirmed,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print("temporary_gallery_ok=true")
    print(f"uploaded_files={len(assets)}")
    print(f"queries={len(query_results)}")
    print("session_isolation=404")
    print("private_cache_control=private,no-store")
    print(f"cleanup_confirmed={str(cleanup_confirmed).lower()}")


if __name__ == "__main__":
    main()
