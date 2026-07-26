#!/usr/bin/env python3
"""Wait for a cold public deployment to become a healthy MuseLens demo."""

from __future__ import annotations

import argparse
import json
import os
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen

from muselens import __version__
from muselens.deployment import validate_deployment_health


OPENAPI_BASE = "https://modelscope.cn/openapi/v1"
FAILED_STATE_MARKERS = {"failed", "error", "stopped", "canceled", "cancelled"}
RUNNING_STATES = {"running"}


def studio_url(studio_id: str, suffix: str = "") -> str:
    owner, separator, name = studio_id.partition("/")
    if not separator or not owner or not name:
        raise ValueError("--studio-id must use the owner/name format")
    return f"{OPENAPI_BASE}/studios/{quote(owner)}/{quote(name)}{suffix}"


def fetch_json(url: str, *, token: str | None = None, timeout: float = 30) -> dict:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers)
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - caller controls URL
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object")
    return payload


def fetch_text(url: str, *, token: str, timeout: float) -> str:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed official URL
        return response.read().decode(errors="replace")


def studio_status(payload: dict) -> str:
    state = payload.get("Data", payload.get("data", payload))
    if not isinstance(state, dict):
        return "unknown"
    value = state.get("Status", state.get("status", "unknown"))
    return str(value).strip() or "unknown"


def is_failed_status(status: str) -> bool:
    normalized = status.casefold()
    return any(marker in normalized for marker in FAILED_STATE_MARKERS)


def fetch_failure_logs(studio_id: str, token: str, request_timeout: float) -> None:
    for log_type in ("build", "run"):
        try:
            detail = fetch_text(
                studio_url(studio_id, f"/logs/{log_type}"),
                token=token,
                timeout=request_timeout,
            )
        except (HTTPError, URLError, TimeoutError) as error:
            detail = str(error)
        print(f"modelscope_{log_type}_log={detail[-12000:]}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Wait for MuseLens deployment health.")
    parser.add_argument("base_url")
    parser.add_argument("--timeout", type=float, default=1800)
    parser.add_argument("--interval", type=float, default=15)
    parser.add_argument("--request-timeout", type=float, default=30)
    parser.add_argument(
        "--studio-id",
        help="ModelScope Studio owner/name; enables build-state polling and fast failure.",
    )
    parser.add_argument(
        "--expected-version",
        default=__version__,
        help="Wait until /health reports this application version.",
    )
    parser.add_argument(
        "--expected-commit",
        help="Wait until /health reports this exact source commit.",
    )
    args = parser.parse_args()
    token = os.environ.get("MODELSCOPE_API_TOKEN")
    if args.studio_id and not token:
        raise SystemExit("MODELSCOPE_API_TOKEN is required with --studio-id.")
    if args.studio_id:
        try:
            studio_url(args.studio_id)
        except ValueError as error:
            raise SystemExit(str(error)) from error

    deadline = monotonic() + args.timeout
    attempt = 0
    last_error = "not started"
    while monotonic() < deadline:
        attempt += 1
        if args.studio_id:
            try:
                status_payload = fetch_json(
                    studio_url(args.studio_id),
                    token=token,
                    timeout=args.request_timeout,
                )
                current_status = studio_status(status_payload)
            except HTTPError as error:
                if error.code in {401, 403, 404}:
                    raise SystemExit(
                        f"Could not inspect ModelScope Studio (HTTP {error.code})."
                    ) from error
                current_status = f"unavailable: HTTP {error.code}"
            except (URLError, TimeoutError, ValueError, json.JSONDecodeError) as error:
                current_status = f"unavailable: {error}"
            normalized_status = current_status.casefold()
            if is_failed_status(current_status):
                fetch_failure_logs(args.studio_id, token, args.request_timeout)
                raise SystemExit(
                    f"ModelScope deployment entered terminal state {current_status!r}."
                )
            if normalized_status not in RUNNING_STATES:
                last_error = f"ModelScope status is {current_status!r}"
                print(
                    f"deployment_wait_attempt={attempt} status=pending detail={last_error}",
                    flush=True,
                )
                sleep(min(args.interval, max(0, deadline - monotonic())))
                continue

        request = Request(
            urljoin(args.base_url.rstrip("/") + "/", "health"),
            headers={"Accept": "application/json"},
        )
        try:
            with urlopen(request, timeout=args.request_timeout) as response:  # noqa: S310
                health = json.load(response)
            validate_deployment_health(health)
            if health.get("version") != args.expected_version:
                raise ValueError(
                    f"Expected version {args.expected_version!r}, got "
                    f"{health.get('version')!r}"
                )
            if args.expected_commit and health.get("commit") != args.expected_commit:
                raise ValueError(
                    f"Expected commit {args.expected_commit!r}, got "
                    f"{health.get('commit')!r}"
                )
        except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as error:
            last_error = str(error)
            print(f"deployment_wait_attempt={attempt} status=pending detail={last_error}", flush=True)
            sleep(min(args.interval, max(0, deadline - monotonic())))
            continue
        print(f"deployment_ready=true attempts={attempt}")
        print(f"version={health['version']}")
        print(f"commit={health.get('commit', 'unknown')}")
        return
    raise SystemExit(f"Deployment did not become healthy before timeout: {last_error}")


if __name__ == "__main__":
    main()
