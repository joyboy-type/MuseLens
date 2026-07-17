#!/usr/bin/env python3
"""Download and prepare the COCO 2017 validation split for retrieval evaluation."""

import argparse
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
IMAGE_ARCHIVE_URL = "http://images.cocodataset.org/zips/val2017.zip"
ANNOTATION_ARCHIVE_URL = (
    "http://images.cocodataset.org/annotations/annotations_trainval2017.zip"
)
DOWNLOAD_CHUNK_BYTES = 1024 * 1024


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare all 5,000 COCO 2017 validation images and retrieval metadata."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "evaluation" / "coco-val2017",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / ".download-cache" / "coco",
    )
    return parser.parse_args()


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(DOWNLOAD_CHUNK_BYTES), b""):
            digest.update(block)
    return digest.hexdigest()


def download_with_resume(url: str, destination: Path, attempts: int = 5) -> Path:
    if destination.is_file():
        try:
            with ZipFile(destination):
                print(f"archive_cached path={destination} size_mb={destination.stat().st_size / 2**20:.1f}")
                return destination
        except BadZipFile:
            print(f"archive_invalid path={destination}; downloading again")
            destination.unlink()

    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        existing = partial.stat().st_size if partial.exists() else 0
        headers = {"User-Agent": "MuseLens/0.1 dataset preparation"}
        if existing:
            headers["Range"] = f"bytes={existing}-"
        try:
            with urlopen(Request(url, headers=headers), timeout=120) as response:
                resumed = existing > 0 and response.status == 206
                mode = "ab" if resumed else "wb"
                downloaded = existing if resumed else 0
                remaining = int(response.headers.get("Content-Length", "0"))
                total = downloaded + remaining if remaining else 0
                started = time.monotonic()
                last_report = started
                with partial.open(mode) as output:
                    while chunk := response.read(DOWNLOAD_CHUNK_BYTES):
                        output.write(chunk)
                        downloaded += len(chunk)
                        now = time.monotonic()
                        if now - last_report >= 2:
                            elapsed = max(now - started, 0.001)
                            progress = f"/{total / 2**20:.1f}" if total else ""
                            print(
                                f"download file={destination.name} mb={downloaded / 2**20:.1f}"
                                f"{progress} speed_mbps={(downloaded - existing) / 2**20 / elapsed:.1f}",
                                flush=True,
                            )
                            last_report = now
            partial.replace(destination)
            with ZipFile(destination) as archive:
                archive.infolist()
            print(
                f"download_complete file={destination.name} "
                f"size_mb={destination.stat().st_size / 2**20:.1f}"
            )
            return destination
        except (HTTPError, URLError, TimeoutError, BadZipFile) as error:
            last_error = error
            if attempt == attempts:
                break
            delay = min(2**attempt, 20)
            print(f"download_retry attempt={attempt}/{attempts} delay={delay}s error={error}")
            time.sleep(delay)
    raise RuntimeError(f"Failed to download {url} after {attempts} attempts") from last_error


def extract_images(archive_path: Path, image_dir: Path) -> int:
    image_dir.mkdir(parents=True, exist_ok=True)
    extracted = 0
    with ZipFile(archive_path) as archive:
        members = sorted(
            (
                member
                for member in archive.infolist()
                if member.filename.startswith("val2017/")
                and member.filename.endswith(".jpg")
            ),
            key=lambda member: member.filename,
        )
        for position, member in enumerate(members, start=1):
            destination = image_dir / Path(member.filename).name
            if destination.is_file() and destination.stat().st_size == member.file_size:
                continue
            with archive.open(member) as source, destination.open("wb") as output:
                shutil.copyfileobj(source, output, length=DOWNLOAD_CHUNK_BYTES)
            extracted += 1
            if position % 500 == 0:
                print(f"extract_images checked={position}/{len(members)} new={extracted}", flush=True)
    if len(members) != 5000:
        raise RuntimeError(f"Expected 5,000 COCO validation images, found {len(members)}")
    print(f"extract_images_complete total={len(members)} new={extracted}")
    return len(members)


def extract_annotations(archive_path: Path, annotation_dir: Path) -> tuple[Path, Path]:
    annotation_dir.mkdir(parents=True, exist_ok=True)
    selected = {
        "annotations/captions_val2017.json": annotation_dir / "captions_val2017.json",
        "annotations/instances_val2017.json": annotation_dir / "instances_val2017.json",
    }
    with ZipFile(archive_path) as archive:
        for member_name, destination in selected.items():
            member = archive.getinfo(member_name)
            if not destination.is_file() or destination.stat().st_size != member.file_size:
                with archive.open(member) as source, destination.open("wb") as output:
                    shutil.copyfileobj(source, output, length=DOWNLOAD_CHUNK_BYTES)
                print(f"extract_annotation file={destination.name}")
    return selected.values()


def build_manifest(
    captions_path: Path,
    instances_path: Path,
    output_path: Path,
) -> int:
    captions_data = json.loads(captions_path.read_text(encoding="utf-8"))
    instances_data = json.loads(instances_path.read_text(encoding="utf-8"))
    captions_by_image: dict[int, list[str]] = defaultdict(list)
    categories_by_image: dict[int, set[str]] = defaultdict(set)
    category_names = {
        category["id"]: category["name"] for category in instances_data["categories"]
    }

    for annotation in captions_data["annotations"]:
        captions_by_image[annotation["image_id"]].append(annotation["caption"])
    for annotation in instances_data["annotations"]:
        categories_by_image[annotation["image_id"]].add(category_names[annotation["category_id"]])

    records = []
    for image in sorted(captions_data["images"], key=lambda item: item["file_name"]):
        image_id = image["id"]
        records.append(
            {
                "image_id": str(image_id),
                "filename": image["file_name"],
                "width": image["width"],
                "height": image["height"],
                "captions": captions_by_image[image_id],
                "categories": sorted(categories_by_image[image_id]),
                "license_id": image["license"],
                "source": image["coco_url"],
            }
        )

    with output_path.open("w", encoding="utf-8") as output:
        for record in records:
            output.write(json.dumps(record, ensure_ascii=False) + "\n")
    if len(records) != 5000:
        raise RuntimeError(f"Expected 5,000 manifest records, found {len(records)}")
    print(f"manifest_complete records={len(records)} path={output_path}")
    return len(records)


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    cache_dir = args.cache_dir.resolve()
    image_archive = download_with_resume(IMAGE_ARCHIVE_URL, cache_dir / "val2017.zip")
    annotation_archive = download_with_resume(
        ANNOTATION_ARCHIVE_URL,
        cache_dir / "annotations_trainval2017.zip",
    )

    images = extract_images(image_archive, output_dir / "images")
    captions_path, instances_path = extract_annotations(
        annotation_archive, output_dir / "annotations"
    )
    records = build_manifest(captions_path, instances_path, output_dir / "manifest.jsonl")
    summary = {
        "dataset": "COCO 2017",
        "split": "validation",
        "images": images,
        "manifest_records": records,
        "selection": "all validation images sorted by filename",
        "image_archive_url": IMAGE_ARCHIVE_URL,
        "annotation_archive_url": ANNOTATION_ARCHIVE_URL,
        "image_archive_sha256": file_sha256(image_archive),
        "annotation_archive_sha256": file_sha256(annotation_archive),
        "manifest_sha256": file_sha256(output_dir / "manifest.jsonl"),
        "license_note": "Each image retains its COCO license_id and source URL in the manifest.",
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted; rerun the command to resume downloads.", file=sys.stderr)
        raise SystemExit(130) from None
