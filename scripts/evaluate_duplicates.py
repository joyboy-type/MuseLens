#!/usr/bin/env python3
"""Evaluate near-duplicate grouping on deterministic COCO image transformations."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from itertools import combinations
import json
from pathlib import Path
import sys
from time import perf_counter

from PIL import Image, ImageOps

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from muselens.duplicates import (  # noqa: E402
    color_distance,
    duplicate_components,
    hash_distance,
    visual_fingerprint,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "evaluation" / "coco-val2017" / "images",
    )
    parser.add_argument(
        "--query-dir",
        type=Path,
        default=(
            PROJECT_ROOT
            / "data"
            / "evaluation"
            / "image-retrieval-coco500-v1"
            / "queries"
        ),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=(
            PROJECT_ROOT
            / "data"
            / "evaluation"
            / "image-retrieval-coco500-v1"
            / "manifest.jsonl"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=(
            PROJECT_ROOT
            / "artifacts"
            / "evaluations"
            / "near-duplicate-coco500-v1.json"
        ),
    )
    parser.add_argument("--hash-distance", type=int, default=8)
    parser.add_argument("--color-distance", type=float, default=45)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records = [json.loads(line) for line in args.manifest.read_text().splitlines() if line]
    source_names = list(dict.fromkeys(record["source_filename"] for record in records))
    entries = [
        (args.source_dir / filename, Path(filename).stem, "original")
        for filename in source_names
    ]
    entries.extend(
        (
            args.query_dir / record["query_filename"],
            Path(record["source_filename"]).stem,
            record["variant"],
        )
        for record in records
    )
    missing = [str(path) for path, _, _ in entries if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing {len(missing)} evaluation images; first: {missing[0]}")

    fingerprint_started = perf_counter()
    fingerprints = []
    for position, (path, _, _) in enumerate(entries, start=1):
        with Image.open(path) as opened:
            fingerprints.append(
                visual_fingerprint(ImageOps.exif_transpose(opened).convert("RGB"))
            )
        if position % 500 == 0:
            print(f"fingerprints={position}/{len(entries)}")
    fingerprint_seconds = perf_counter() - fingerprint_started

    grouping_started = perf_counter()
    groups = duplicate_components(
        fingerprints,
        max_hash_distance=args.hash_distance,
        max_color_distance=args.color_distance,
    )
    grouping_seconds = perf_counter() - grouping_started

    labels = [label for _, label, _ in entries]
    variants = [variant for _, _, variant in entries]
    predicted_pairs = {
        tuple(sorted(pair))
        for group in groups
        for pair in combinations(group, 2)
    }
    label_positions: dict[str, list[int]] = {}
    for position, label in enumerate(labels):
        label_positions.setdefault(label, []).append(position)
    true_pairs = {
        pair
        for positions in label_positions.values()
        for pair in combinations(positions, 2)
    }
    true_positives = len(predicted_pairs & true_pairs)
    false_positives = len(predicted_pairs - true_pairs)
    false_negatives = len(true_pairs - predicted_pairs)
    precision = true_positives / max(1, true_positives + false_positives)
    recall = true_positives / max(1, true_positives + false_negatives)
    f1 = 2 * precision * recall / max(1e-12, precision + recall)

    source_positions = {label: position for position, label in enumerate(labels[: len(source_names)])}
    direct_by_variant: dict[str, dict[str, int | float]] = {}
    for variant in sorted(set(variants) - {"original"}):
        positions = [position for position, value in enumerate(variants) if value == variant]
        matched = 0
        for position in positions:
            source_position = source_positions[labels[position]]
            if (
                hash_distance(
                    fingerprints[position].perceptual_hash,
                    fingerprints[source_position].perceptual_hash,
                )
                <= args.hash_distance
                and color_distance(
                    fingerprints[position].average_color,
                    fingerprints[source_position].average_color,
                )
                <= args.color_distance
            ):
                matched += 1
        direct_by_variant[variant] = {
            "matched": matched,
            "total": len(positions),
            "recall": matched / max(1, len(positions)),
        }

    mixed_groups = sum(len({labels[position] for position in group}) > 1 for group in groups)
    result = {
        "experiment": "near-duplicate-coco500",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "protocol": {
            "source_images": len(source_names),
            "transformed_images": len(records),
            "variants": dict(Counter(variants)),
            "hash_distance": args.hash_distance,
            "color_distance": args.color_distance,
        },
        "pair_metrics": {
            "true_positives": true_positives,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        },
        "groups": {
            "detected": len(groups),
            "mixed_source_groups": mixed_groups,
            "largest_group": max((len(group) for group in groups), default=0),
        },
        "direct_source_match_by_variant": direct_by_variant,
        "performance": {
            "fingerprint_seconds": fingerprint_seconds,
            "grouping_seconds": grouping_seconds,
            "images_per_second": len(entries) / fingerprint_seconds,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"output={args.output}")


if __name__ == "__main__":
    main()
