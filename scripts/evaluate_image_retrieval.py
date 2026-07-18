#!/usr/bin/env python3
"""Evaluate image-to-image retrieval against deterministic COCO perturbations."""

from __future__ import annotations

import argparse
from io import BytesIO
import json
from pathlib import Path
import random
import sys
from time import perf_counter

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from muselens.config import settings  # noqa: E402
from muselens.encoder import ClipEncoder  # noqa: E402
from muselens.evaluation import retrieval_metrics  # noqa: E402
from muselens.index import normalize  # noqa: E402


VARIANTS = ("center_crop", "jpeg_low", "blur", "dark", "low_resolution")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "evaluation" / "coco-val2017" / "images",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "evaluation" / "image-retrieval-coco500-v1",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "artifacts" / "evaluations" / "image-retrieval-coco500-v1.json",
    )
    parser.add_argument("--count", type=int, default=500)
    parser.add_argument("--seed", type=int, default=20260718)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--model-id", default=settings.clip_model_id)
    parser.add_argument("--regenerate", action="store_true")
    return parser.parse_args()


def normalized_rows(matrix: np.ndarray) -> np.ndarray:
    return np.stack([normalize(row) for row in matrix])


def center_crop(image: Image.Image) -> Image.Image:
    width, height = image.size
    crop_width = max(1, round(width * 0.68))
    crop_height = max(1, round(height * 0.68))
    left = (width - crop_width) // 2
    top = (height - crop_height) // 2
    return image.crop((left, top, left + crop_width, top + crop_height)).resize(
        (width, height), Image.Resampling.LANCZOS
    )


def jpeg_low(image: Image.Image) -> Image.Image:
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=24, optimize=True)
    buffer.seek(0)
    with Image.open(buffer) as decoded:
        return decoded.convert("RGB")


def low_resolution(image: Image.Image) -> Image.Image:
    width, height = image.size
    scale = min(96 / max(width, height), 1.0)
    small = image.resize(
        (max(1, round(width * scale)), max(1, round(height * scale))),
        Image.Resampling.BILINEAR,
    )
    return small.resize((width, height), Image.Resampling.BILINEAR)


def transform(image: Image.Image, variant: str) -> Image.Image:
    if variant == "center_crop":
        return center_crop(image)
    if variant == "jpeg_low":
        return jpeg_low(image)
    if variant == "blur":
        return image.filter(ImageFilter.GaussianBlur(radius=3.2))
    if variant == "dark":
        return ImageEnhance.Brightness(image).enhance(0.48)
    if variant == "low_resolution":
        return low_resolution(image)
    raise ValueError(f"Unknown variant: {variant}")


def prepare_queries(
    source_paths: list[Path],
    work_dir: Path,
    regenerate: bool,
) -> list[dict]:
    query_dir = work_dir / "queries"
    query_dir.mkdir(parents=True, exist_ok=True)
    records = []
    total = len(source_paths) * len(VARIANTS)
    generated = 0
    for source_position, source_path in enumerate(source_paths):
        with Image.open(source_path) as opened:
            source = opened.convert("RGB")
        try:
            for variant in VARIANTS:
                filename = f"{source_path.stem}--{variant}.jpg"
                destination = query_dir / filename
                if regenerate or not destination.is_file():
                    changed = transform(source, variant)
                    try:
                        changed.save(destination, format="JPEG", quality=90, optimize=True)
                    finally:
                        changed.close()
                    generated += 1
                records.append(
                    {
                        "query_filename": filename,
                        "source_filename": source_path.name,
                        "source_position": source_position,
                        "variant": variant,
                    }
                )
        finally:
            source.close()
        if (source_position + 1) % 50 == 0 or source_position + 1 == len(source_paths):
            print(
                f"prepare_sources={source_position + 1}/{len(source_paths)} "
                f"queries_ready={(source_position + 1) * len(VARIANTS)}/{total}"
            )

    manifest = work_dir / "manifest.jsonl"
    manifest.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    print(f"generated={generated} reused={total - generated} manifest={manifest}")
    return records


def encode_paths(
    encoder: ClipEncoder,
    paths: list[Path],
    batch_size: int,
    label: str,
) -> np.ndarray:
    vectors = []
    for start in range(0, len(paths), batch_size):
        batch_paths = paths[start : start + batch_size]
        images = []
        try:
            for path in batch_paths:
                with Image.open(path) as opened:
                    images.append(opened.convert("RGB"))
            vectors.append(encoder.encode_images(images))
        finally:
            for image in images:
                image.close()
        encoded = min(start + batch_size, len(paths))
        if encoded % (batch_size * 5) == 0 or encoded == len(paths):
            print(f"{label}_encoded={encoded}/{len(paths)}")
    return normalized_rows(np.concatenate(vectors))


def metrics_by_variant(
    similarities: np.ndarray,
    records: list[dict],
    relevant: np.ndarray,
) -> dict[str, dict[str, float]]:
    variants = np.array([record["variant"] for record in records])
    return {
        variant: retrieval_metrics(similarities[variants == variant], relevant[variants == variant])
        for variant in VARIANTS
    }


def product_policy_metrics(
    similarities: np.ndarray,
    relevant: np.ndarray,
    margin: float,
    top_k: int = 12,
) -> dict[str, float]:
    limit = min(top_k, similarities.shape[1])
    positions = np.argpartition(-similarities, kth=limit - 1, axis=1)[:, :limit]
    candidate_scores = np.take_along_axis(similarities, positions, axis=1)
    order = np.argsort(-candidate_scores, axis=1)
    ranked = np.take_along_axis(positions, order, axis=1)
    ranked_scores = np.take_along_axis(candidate_scores, order, axis=1)
    retained = ranked_scores >= (ranked_scores[:, :1] - margin)
    returned = retained.sum(axis=1)
    top_five_retained = retained & (np.arange(limit)[None, :] < 5)
    relevant_in_top_five = np.any(
        (ranked == relevant[:, None]) & top_five_retained,
        axis=1,
    )
    return {
        "relative_margin": margin,
        "recall_at_5_after_policy": float(np.mean(relevant_in_top_five)),
        "empty_result_rate": float(np.mean(returned == 0)),
        "average_results": float(np.mean(returned)),
        "p95_results": float(np.percentile(returned, 95)),
    }


def main() -> None:
    args = parse_args()
    if args.count < 10 or args.batch_size < 1:
        raise ValueError("--count must be at least 10 and --batch-size must be positive")
    available = sorted(args.source_dir.glob("*.jpg"))
    if len(available) < args.count:
        raise FileNotFoundError(
            f"Need {args.count} source images in {args.source_dir}, found {len(available)}"
        )
    randomizer = random.Random(args.seed)
    source_paths = sorted(randomizer.sample(available, args.count))
    records = prepare_queries(source_paths, args.work_dir, args.regenerate)
    query_paths = [args.work_dir / "queries" / record["query_filename"] for record in records]
    relevant = np.array([record["source_position"] for record in records])

    encoder = ClipEncoder(args.model_id)
    load_started = perf_counter()
    encoder.load()
    model_load_seconds = perf_counter() - load_started
    print(f"model={args.model_id} device={encoder.device} load_seconds={model_load_seconds:.2f}")

    gallery_started = perf_counter()
    gallery_vectors = encode_paths(encoder, source_paths, args.batch_size, "gallery")
    gallery_seconds = perf_counter() - gallery_started
    query_started = perf_counter()
    query_vectors = encode_paths(encoder, query_paths, args.batch_size, "query")
    query_seconds = perf_counter() - query_started

    search_started = perf_counter()
    similarities = query_vectors @ gallery_vectors.T
    rankings = np.argsort(-similarities, axis=1)
    search_seconds = perf_counter() - search_started
    ranks = np.argmax(rankings == relevant[:, None], axis=1) + 1

    margins = (0.015, 0.025, 0.035, 0.05, 0.075)
    result = {
        "experiment": "image-to-image-robustness-coco500-v1",
        "model_id": args.model_id,
        "device": str(encoder.device),
        "source": str(args.source_dir.relative_to(PROJECT_ROOT)),
        "work_dir": str(args.work_dir.relative_to(PROJECT_ROOT)),
        "seed": args.seed,
        "gallery_images": len(source_paths),
        "query_images": len(query_paths),
        "variants": list(VARIANTS),
        "metrics": retrieval_metrics(similarities, relevant),
        "metrics_by_variant": metrics_by_variant(similarities, records, relevant),
        "rank_distribution": {
            "worst_rank": int(ranks.max()),
            "p95_rank": float(np.percentile(ranks, 95)),
        },
        "product_policy_comparison": [
            product_policy_metrics(similarities, relevant, margin) for margin in margins
        ],
        "timing_seconds": {
            "model_load": model_load_seconds,
            "gallery_encoding_total": gallery_seconds,
            "gallery_encoding_per_image": gallery_seconds / len(source_paths),
            "query_encoding_total": query_seconds,
            "query_encoding_per_image": query_seconds / len(query_paths),
            "matrix_search_total": search_seconds,
            "matrix_search_per_query": search_seconds / len(query_paths),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"saved={args.output}")


if __name__ == "__main__":
    main()
