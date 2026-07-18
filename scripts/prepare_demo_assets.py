#!/usr/bin/env python3
"""Build a small, attributed, searchable corpus for the public Docker Space."""

from __future__ import annotations

import argparse
from collections import defaultdict
from hashlib import sha256
import json
import mimetypes
from pathlib import Path
import re
import shutil
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from muselens.encoder import ClipEncoder  # noqa: E402
from muselens.index import VectorIndex  # noqa: E402
from muselens.library import ImageLibrary, prepare_image  # noqa: E402
from muselens.repository import ImageRepository  # noqa: E402


LICENSE_ID = 4
LICENSE_NAME = "CC BY 2.0"
LICENSE_URL = "https://creativecommons.org/licenses/by/2.0/"
TARGET_CATEGORIES = (
    "dog",
    "cat",
    "bird",
    "horse",
    "elephant",
    "car",
    "bus",
    "train",
    "airplane",
    "boat",
    "pizza",
    "cake",
    "apple",
    "sports ball",
    "surfboard",
    "snowboard",
    "chair",
    "bed",
    "laptop",
    "cell phone",
    "book",
    "clock",
)
BASE58 = "123456789abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an attributed COCO/Flickr demo corpus and its search index."
    )
    parser.add_argument(
        "--coco-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "evaluation" / "coco-val2017",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "demo_assets",
    )
    parser.add_argument("--count", type=int, default=24)
    parser.add_argument("--model-id", default="google/siglip2-base-patch16-224")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def encode_base58(value: int) -> str:
    encoded = ""
    while value:
        value, remainder = divmod(value, 58)
        encoded = BASE58[remainder] + encoded
    return encoded or BASE58[0]


def flickr_photo_id(static_url: str) -> int:
    match = re.search(r"/(\d+)_", static_url)
    if not match:
        raise ValueError(f"Could not extract a Flickr photo id from {static_url}")
    return int(match.group(1))


def fetch_flickr_metadata(static_url: str) -> dict[str, Any]:
    photo_id = flickr_photo_id(static_url)
    short_url = f"https://flic.kr/p/{encode_base58(photo_id)}"
    endpoint = "https://www.flickr.com/services/oembed/?" + urlencode(
        {"url": short_url, "format": "json"}
    )
    request = Request(endpoint, headers={"User-Agent": "MuseLens-demo-builder/1.0"})
    with urlopen(request, timeout=20) as response:  # noqa: S310 - fixed HTTPS endpoint
        metadata = json.load(response)
    if str(metadata.get("license_id")) != str(LICENSE_ID):
        raise ValueError(
            f"Flickr license changed for photo {photo_id}: {metadata.get('license')}"
        )
    return metadata


def read_coco(coco_dir: Path) -> tuple[list[dict[str, Any]], dict[int, set[str]]]:
    annotations = coco_dir / "annotations"
    captions = json.loads((annotations / "captions_val2017.json").read_text())
    instances = json.loads((annotations / "instances_val2017.json").read_text())
    category_names = {item["id"]: item["name"] for item in instances["categories"]}
    categories_by_image: dict[int, set[str]] = defaultdict(set)
    for annotation in instances["annotations"]:
        categories_by_image[annotation["image_id"]].add(
            category_names[annotation["category_id"]]
        )
    images = [
        item
        for item in captions["images"]
        if item["license"] == LICENSE_ID
        and (coco_dir / "images" / item["file_name"]).is_file()
    ]
    return images, categories_by_image


def select_images(
    images: list[dict[str, Any]],
    categories_by_image: dict[int, set[str]],
    count: int,
) -> list[dict[str, Any]]:
    if count < 1:
        raise ValueError("--count must be at least 1")
    if len(images) < count:
        raise ValueError(f"Only {len(images)} eligible CC BY 2.0 images are available")

    remaining = {item["id"]: item for item in images}
    selected: list[dict[str, Any]] = []
    covered: set[str] = set()

    for target in TARGET_CATEGORIES:
        if len(selected) >= count:
            break
        candidates = [
            item
            for item in remaining.values()
            if target in categories_by_image[item["id"]]
        ]
        if not candidates:
            continue
        chosen = max(
            candidates,
            key=lambda item: (
                len(categories_by_image[item["id"]] - covered),
                len(categories_by_image[item["id"]]),
                -item["id"],
            ),
        )
        selected.append(chosen)
        covered.update(categories_by_image[chosen["id"]])
        remaining.pop(chosen["id"])

    while len(selected) < count:
        chosen = max(
            remaining.values(),
            key=lambda item: (
                len(categories_by_image[item["id"]] - covered),
                len(categories_by_image[item["id"]]),
                -item["id"],
            ),
        )
        selected.append(chosen)
        covered.update(categories_by_image[chosen["id"]])
        remaining.pop(chosen["id"])
    return selected


def reset_output(output_dir: Path, force: bool) -> None:
    generated = (
        output_dir / "images",
        output_dir / "state",
        output_dir / "thumbnails",
        output_dir / "manifest.json",
        output_dir / "ATTRIBUTIONS.md",
    )
    existing = [path for path in generated if path.exists()]
    if existing and not force:
        raise FileExistsError("Generated demo assets already exist; pass --force to rebuild")
    for path in existing:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    output_dir.mkdir(parents=True, exist_ok=True)


def build_assets(args: argparse.Namespace) -> list[dict[str, Any]]:
    coco_dir = args.coco_dir.resolve()
    output_dir = args.output_dir.resolve()
    reset_output(output_dir, args.force)
    images, categories_by_image = read_coco(coco_dir)
    ranked = select_images(images, categories_by_image, len(images))
    selected: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for item in ranked:
        try:
            flickr = fetch_flickr_metadata(item["flickr_url"])
        except (HTTPError, URLError, TimeoutError, ValueError, KeyError) as error:
            print(f"[skip] {item['file_name']}: attribution unavailable ({error})")
            continue
        selected.append((item, flickr))
        if len(selected) == args.count:
            break
    if len(selected) != args.count:
        raise RuntimeError(
            f"Only {len(selected)} images retained verifiable Flickr attribution"
        )

    image_dir = output_dir / "images"
    state_dir = output_dir / "state"
    thumbnail_dir = output_dir / "thumbnails"
    repository = ImageRepository(state_dir / "index.sqlite3")
    repository.initialize()
    encoder = ClipEncoder(args.model_id)
    library = ImageLibrary(
        image_dir,
        repository,
        VectorIndex(),
        encoder,
        thumbnail_dir=thumbnail_dir,
    )

    records: list[dict[str, Any]] = []
    for position, (item, flickr) in enumerate(selected, start=1):
        source = coco_dir / "images" / item["file_name"]
        content = source.read_bytes()
        content_type = mimetypes.guess_type(source.name)[0] or "image/jpeg"
        candidate = prepare_image(
            source.name,
            content_type,
            content,
            max_upload_bytes=12 * 1024 * 1024,
        )
        try:
            result = library.import_candidates([candidate])[0]
        finally:
            candidate.image.close()
        records.append(
            {
                "position": position,
                "image_id": result.stored.image.image_id,
                "stored_filename": result.stored.stored_filename,
                "original_filename": source.name,
                "sha256": sha256(content).hexdigest(),
                "title": flickr.get("title") or source.stem,
                "creator": flickr["author_name"],
                "creator_url": flickr["author_url"],
                "source_url": flickr["web_page"],
                "coco_url": item["coco_url"],
                "license": LICENSE_NAME,
                "license_url": LICENSE_URL,
                "license_id": LICENSE_ID,
                "categories": sorted(categories_by_image[item["id"]]),
                "modified": False,
            }
        )
        print(f"[{position:02d}/{len(selected):02d}] {source.name} -> {result.stored.stored_filename}")

    manifest = {
        "name": "MuseLens public demo corpus",
        "source_dataset": "COCO 2017 validation / original Flickr photos",
        "selection": "Deterministic category-diverse subset restricted to Flickr CC BY 2.0",
        "model_id": args.model_id,
        "image_count": len(records),
        "license_note": (
            "Each image remains under its creator's CC BY 2.0 license. "
            "No image pixels were modified."
        ),
        "images": records,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )
    attribution_lines = [
        "# Demo image attributions",
        "",
        (
            "These unmodified images are used in the MuseLens public demo under "
            f"[{LICENSE_NAME}]({LICENSE_URL})."
        ),
        "",
    ]
    for record in records:
        attribution_lines.append(
            f"- [{record['title']}]({record['source_url']}) by "
            f"[{record['creator']}]({record['creator_url']}) — "
            f"[{LICENSE_NAME}]({LICENSE_URL})"
        )
    (output_dir / "ATTRIBUTIONS.md").write_text("\n".join(attribution_lines) + "\n")
    return records


def main() -> None:
    args = parse_args()
    records = build_assets(args)
    print(f"demo_assets={args.output_dir.resolve()}")
    print(f"image_count={len(records)}")


if __name__ == "__main__":
    main()
