#!/usr/bin/env python3
"""Wait for a cold public deployment to become a healthy MuseLens demo."""

from __future__ import annotations

import argparse
import json
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from muselens.deployment import validate_deployment_health


def main() -> None:
    parser = argparse.ArgumentParser(description="Wait for MuseLens deployment health.")
    parser.add_argument("base_url")
    parser.add_argument("--timeout", type=float, default=1800)
    parser.add_argument("--interval", type=float, default=15)
    parser.add_argument("--request-timeout", type=float, default=30)
    args = parser.parse_args()

    deadline = monotonic() + args.timeout
    attempt = 0
    last_error = "not started"
    while monotonic() < deadline:
        attempt += 1
        request = Request(
            urljoin(args.base_url.rstrip("/") + "/", "health"),
            headers={"Accept": "application/json"},
        )
        try:
            with urlopen(request, timeout=args.request_timeout) as response:  # noqa: S310
                health = json.load(response)
            validate_deployment_health(health)
        except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as error:
            last_error = str(error)
            print(f"deployment_wait_attempt={attempt} status=pending detail={last_error}", flush=True)
            sleep(min(args.interval, max(0, deadline - monotonic())))
            continue
        print(f"deployment_ready=true attempts={attempt}")
        return
    raise SystemExit(f"Deployment did not become healthy before timeout: {last_error}")


if __name__ == "__main__":
    main()
