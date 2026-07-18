#!/usr/bin/env python3
"""Publish a packaged MuseLens tree to a ModelScope Docker Studio."""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


OPENAPI_BASE = "https://modelscope.cn/openapi/v1"
REPO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
REQUIRED_FILES = ("Dockerfile", "README.md", "ms_deploy.json", "pyproject.toml")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish MuseLens to ModelScope Studio.")
    parser.add_argument("source", type=Path)
    parser.add_argument("--repo-id", help="ModelScope Studio owner/name.")
    parser.add_argument("--repo-url", help="Override the Git remote URL (primarily for testing).")
    parser.add_argument("--branch", default="master")
    parser.add_argument("--deploy", action="store_true", help="Trigger Studio deployment via OpenAPI.")
    parser.add_argument("--dry-run", action="store_true", help="Validate without pushing or deploying.")
    return parser.parse_args()


def validate_source(source: Path) -> None:
    if not source.is_dir():
        raise ValueError(f"Packaged source does not exist: {source}")
    missing = [name for name in REQUIRED_FILES if not (source / name).is_file()]
    if missing:
        raise ValueError(f"Packaged source is missing required files: {missing}")
    deployment = json.loads((source / "ms_deploy.json").read_text())
    variables = {
        item["name"]: item["value"]
        for item in deployment.get("environment_variables", [])
    }
    if deployment.get("sdk_type") != "docker" or deployment.get("port") != 7860:
        raise ValueError("ModelScope release must be a Docker Studio on port 7860")
    if variables.get("MUSELENS_MODE") != "demo":
        raise ValueError("ModelScope release must force MUSELENS_MODE=demo")


def repository_url(repo_id: str) -> str:
    if not REPO_ID_PATTERN.fullmatch(repo_id):
        raise ValueError("--repo-id must use the owner/name format")
    owner, name = repo_id.split("/", 1)
    return f"https://www.modelscope.cn/studios/{quote(owner)}/{quote(name)}.git"


def git_environment(token: str | None, askpass: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment["GIT_TERMINAL_PROMPT"] = "0"
    if token:
        askpass.write_text(
            "#!/bin/sh\n"
            'case "$1" in\n'
            '  *Username*) printf "%s\\n" "$MODELSCOPE_GIT_USERNAME" ;;\n'
            '  *) printf "%s\\n" "$MODELSCOPE_API_TOKEN" ;;\n'
            "esac\n"
        )
        askpass.chmod(0o700)
        environment["GIT_ASKPASS"] = str(askpass)
        environment["MODELSCOPE_GIT_USERNAME"] = "oauth2"
        environment["MODELSCOPE_API_TOKEN"] = token
    return environment


def run_git(arguments: list[str], *, environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


def replace_worktree(worktree: Path, source: Path) -> None:
    for child in worktree.iterdir():
        if child.name != ".git":
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    for child in source.iterdir():
        destination = worktree / child.name
        if child.is_dir():
            shutil.copytree(child, destination)
        else:
            shutil.copy2(child, destination)


def publish_git(source: Path, remote_url: str, branch: str, token: str | None) -> bool:
    with tempfile.TemporaryDirectory(prefix="muselens-modelscope-") as temporary:
        temporary_path = Path(temporary)
        environment = git_environment(token, temporary_path / "askpass.sh")
        worktree = temporary_path / "studio"
        run_git(["clone", "--depth", "1", "--branch", branch, remote_url, str(worktree)], environment=environment)
        replace_worktree(worktree, source)
        run_git(["-C", str(worktree), "add", "--all"], environment=environment)
        status = run_git(
            ["-C", str(worktree), "status", "--porcelain"],
            environment=environment,
        ).stdout
        if not status.strip():
            return False
        run_git(
            [
                "-C",
                str(worktree),
                "-c",
                "user.name=MuseLens Deploy Bot",
                "-c",
                "user.email=deploy@muselens.local",
                "commit",
                "-m",
                "Deploy MuseLens from GitHub",
            ],
            environment=environment,
        )
        run_git(["-C", str(worktree), "push", "origin", f"HEAD:{branch}"], environment=environment)
        return True


def trigger_deployment(repo_id: str, token: str) -> Any:
    owner, name = repo_id.split("/", 1)
    request = Request(
        f"{OPENAPI_BASE}/studios/{quote(owner)}/{quote(name)}/deploy",
        data=b"{}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=60) as response:  # noqa: S310 - fixed official URL
            payload = response.read()
    except HTTPError as error:
        detail = error.read().decode(errors="replace")
        raise RuntimeError(f"ModelScope deployment returned HTTP {error.code}: {detail}") from error
    except (URLError, TimeoutError) as error:
        raise RuntimeError(f"Could not reach ModelScope deployment API: {error}") from error
    if not payload:
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return {"response_base64": base64.b64encode(payload).decode()}


def main() -> None:
    args = parse_args()
    source = args.source.resolve()
    try:
        validate_source(source)
        if not args.repo_url and not args.repo_id:
            raise ValueError("Provide --repo-id or --repo-url")
        if args.repo_id and not REPO_ID_PATTERN.fullmatch(args.repo_id):
            raise ValueError("--repo-id must use the owner/name format")
        if args.deploy and not args.repo_id:
            raise ValueError("--deploy requires --repo-id")
        remote_url = args.repo_url or repository_url(args.repo_id)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"ModelScope release validation failed: {error}") from error

    token = os.environ.get("MODELSCOPE_API_TOKEN")
    is_official_remote = remote_url.startswith("https://www.modelscope.cn/")
    if not args.dry_run and is_official_remote and not token:
        raise SystemExit("MODELSCOPE_API_TOKEN is required for a ModelScope push.")
    if args.deploy and not token:
        raise SystemExit("MODELSCOPE_API_TOKEN is required to trigger deployment.")

    if args.dry_run:
        print("modelscope_release_valid=true")
        print(f"remote={remote_url}")
        return

    try:
        changed = publish_git(source, remote_url, args.branch, token)
        deployment = trigger_deployment(args.repo_id, token) if args.deploy else None
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"ModelScope publish failed: {error}") from error
    print(f"modelscope_push_changed={str(changed).lower()}")
    if args.deploy:
        print("modelscope_deploy_triggered=true")
        if deployment is not None:
            print(json.dumps(deployment, ensure_ascii=False))


if __name__ == "__main__":
    main()
