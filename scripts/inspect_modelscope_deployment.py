#!/usr/bin/env python3
"""Print ModelScope Studio status and authenticated build/runtime logs."""

from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


OWNER = "sinbaby"
NAME = "MuseLens"
PUBLIC_STATUS_URL = (
    f"https://modelscope.cn/api/v1/studio/{quote(OWNER)}/{quote(NAME)}/status"
)
OPENAPI_BASE = (
    f"https://modelscope.cn/openapi/v1/studios/{quote(OWNER)}/{quote(NAME)}"
)


def fetch(url: str, token: str | None = None) -> tuple[int, str]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=60) as response:  # noqa: S310 - official URLs
            return response.status, response.read().decode(errors="replace")
    except HTTPError as error:
        return error.code, error.read().decode(errors="replace")
    except (URLError, TimeoutError) as error:
        return 0, str(error)


def main() -> None:
    token = os.environ.get("MODELSCOPE_API_TOKEN")
    if not token:
        raise SystemExit("MODELSCOPE_API_TOKEN is required.")

    status_code, status_body = fetch(PUBLIC_STATUS_URL)
    print(f"public_status_http={status_code}")
    try:
        payload = json.loads(status_body)
        state = payload.get("Data", payload)
        print(f"studio_status={state.get('Status', 'unknown')}")
    except json.JSONDecodeError:
        print(status_body[:2000])

    for log_type in ("build", "run"):
        code, body = fetch(f"{OPENAPI_BASE}/logs/{log_type}", token)
        print(f"\n--- {log_type} log (HTTP {code}) ---")
        print(body[-30_000:])


if __name__ == "__main__":
    main()
