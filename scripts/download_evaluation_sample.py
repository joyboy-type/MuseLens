#!/usr/bin/env python3
import argparse
import csv
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import time
from typing import Any
from urllib.request import urlopen
from uuid import uuid4

from huggingface_hub import hf_hub_download


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ID = "intro/flickr8k"


def download_with_retry(filename: str, attempts: int = 5) -> Path:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            if mirror := os.getenv("MUSELENS_HF_MIRROR"):
                destination = PROJECT_ROOT / "data" / ".download-cache" / filename
                if destination.is_file():
                    return destination
                destination.parent.mkdir(parents=True, exist_ok=True)
                temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.part")
                try:
                    url = (
                        f"{mirror.rstrip('/')}/datasets/{REPOSITORY_ID}/resolve/main/{filename}"
                    )
                    with urlopen(url, timeout=120) as response, temporary.open("wb") as output:
                        shutil.copyfileobj(response, output, length=1024 * 1024)
                    temporary.replace(destination)
                finally:
                    temporary.unlink(missing_ok=True)
                return destination
            return Path(
                hf_hub_download(
                    repo_id=REPOSITORY_ID,
                    filename=filename,
                    repo_type="dataset",
                )
            )
        except Exception as error:
            last_error = error
            if attempt == attempts:
                break
            delay = min(2**attempt, 20)
            print(f"Retry {attempt}/{attempts} for {filename} after {delay}s: {error}")
            time.sleep(delay)
    raise RuntimeError(f"Failed to download {filename} after {attempts} attempts") from last_error


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download a reproducible Flickr8k sample.")
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--split", choices=("train", "validation", "test"), default="test")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Defaults to the evaluation path for test and data/training otherwise.",
    )
    parser.add_argument("--workers", type=int, default=6)
    return parser.parse_args()


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download_image(
    row: dict[str, str],
    image_dir: Path,
    split: str,
) -> dict[str, Any]:
    filename = row["file_name"]
    cached_path = download_with_retry(f"{split}/{filename}")
    destination = image_dir / filename
    shutil.copy2(cached_path, destination)
    return {
        "image_id": destination.stem,
        "filename": filename,
        "sha256": file_sha256(destination),
        "captions": [row[f"caption_{index}"] for index in range(5)],
        "source": f"hf://datasets/{REPOSITORY_ID}/{split}/{filename}",
    }


def main() -> None:
    args = parse_args()
    if args.count < 1:
        raise ValueError("--count must be at least 1")
    output_dir = args.output_dir or (
        PROJECT_ROOT / "data" / "evaluation" / "sample-v1"
        if args.split == "test"
        else PROJECT_ROOT / "data" / "training" / f"flickr8k-{args.split}-v1"
    )
    image_dir = output_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    repository_split = "dev" if args.split == "validation" else args.split

    metadata_path = download_with_retry(f"{repository_split}/metadata.csv")
    with metadata_path.open(encoding="utf-8", newline="") as file:
        rows = sorted(csv.DictReader(file), key=lambda row: row["file_name"])[: args.count]

    print(f"Downloading {len(rows)} images with {args.workers} workers into {image_dir}")
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        records = list(
            executor.map(
                lambda row: download_image(row, image_dir, repository_split),
                rows,
            )
        )

    manifest_path = output_dir / "manifest.jsonl"
    with manifest_path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")

    summary = {
        "dataset": REPOSITORY_ID,
        "split": args.split,
        "repository_directory": repository_split,
        "license_from_dataset_card": "CC0",
        "sample_rule": "sort file_name ascending and take first N rows",
        "images": len(records),
        "captions_per_image": 5,
        "manifest_sha256": file_sha256(manifest_path),
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    total_bytes = sum((image_dir / record["filename"]).stat().st_size for record in records)
    print(f"Completed: images={len(records)} size_mb={total_bytes / 1024 / 1024:.1f}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
