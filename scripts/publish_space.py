from __future__ import annotations

import argparse
import os
from pathlib import Path

from huggingface_hub import HfApi


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish a packaged MuseLens Docker Space.")
    parser.add_argument("source", type=Path)
    parser.add_argument("--repo-id", default="sinbaby/MuseLens")
    parser.add_argument("--revision", default="main")
    args = parser.parse_args()

    token = os.environ.get("HF_TOKEN")
    if not token:
        raise SystemExit("HF_TOKEN is required.")

    api = HfApi(token=token)
    api.create_repo(
        repo_id=args.repo_id,
        repo_type="space",
        space_sdk="docker",
        exist_ok=True,
        private=False,
    )
    api.upload_folder(
        folder_path=args.source,
        repo_id=args.repo_id,
        repo_type="space",
        revision=args.revision,
        commit_message="Deploy MuseLens from GitHub",
    )
