#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import sys

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from evaluate_retrieval import (  # noqa: E402
    encode_images,
    encode_texts,
    normalize_rows,
    read_manifest,
)
from muselens.config import settings  # noqa: E402
from muselens.encoder import ClipEncoder  # noqa: E402
from muselens.evaluation import (  # noqa: E402
    RejectionPolicy,
    calibrate_rejection_policy,
    rejection_metrics,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate irrelevant-query rejection.")
    parser.add_argument(
        "--sample-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "evaluation" / "sample-v1",
    )
    parser.add_argument("--model-id", default=settings.clip_model_id)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT
        / "artifacts"
        / "evaluations"
        / "clip-vit-b32-rejection-v1.json",
    )
    return parser.parse_args()


def policy_dict(policy: RejectionPolicy) -> dict[str, float]:
    return {
        "absolute_floor": policy.absolute_floor,
        "minimum_z_score": policy.minimum_z_score,
    }


def main() -> None:
    args = parse_args()
    records = read_manifest(args.sample_dir / "manifest.jsonl")
    negative_queries = json.loads(
        (args.sample_dir / "negative_queries.json").read_text(encoding="utf-8")
    )
    image_paths = [args.sample_dir / "images" / record["filename"] for record in records]
    captions = [caption for record in records for caption in record["captions"]]
    relevant = np.repeat(np.arange(len(records)), 5)

    encoder = ClipEncoder(args.model_id)
    image_vectors = normalize_rows(encode_images(encoder, image_paths, args.batch_size))
    text_vectors = normalize_rows(
        encode_texts(encoder, captions + negative_queries, args.batch_size * 4)
    )
    similarities = text_vectors @ image_vectors.T
    positive = similarities[: len(captions)]
    negative = similarities[len(captions) :]

    positive_calibration = np.arange(len(positive)) % 2 == 0
    negative_calibration = np.arange(len(negative)) % 2 == 0
    positive_evaluation = ~positive_calibration
    negative_evaluation = ~negative_calibration
    # Cosine scales differ substantially across CLIP-compatible model families.
    floors = np.arange(-0.20, 0.351, 0.005)

    fixed_policy, fixed_calibration_metrics = calibrate_rejection_policy(
        positive[positive_calibration],
        relevant[positive_calibration],
        negative[negative_calibration],
        floors,
    )
    adaptive_policy, adaptive_calibration_metrics = calibrate_rejection_policy(
        positive[positive_calibration],
        relevant[positive_calibration],
        negative[negative_calibration],
        floors,
        np.arange(0.0, 4.01, 0.1),
    )
    legacy_policy = RejectionPolicy(settings.search_min_score)

    policies = {
        "legacy_fixed": legacy_policy,
        "calibrated_fixed": fixed_policy,
        "adaptive_z_score": adaptive_policy,
    }
    result = {
        "experiment": "irrelevant-query-rejection-v1",
        "model_id": args.model_id,
        "device": str(encoder.device),
        "sample": str(args.sample_dir.relative_to(PROJECT_ROOT)),
        "images": len(records),
        "positive_queries": len(captions),
        "negative_queries": len(negative_queries),
        "split": "alternating calibration/evaluation split",
        "policies": {},
    }
    for name, policy in policies.items():
        result["policies"][name] = {
            "parameters": policy_dict(policy),
            "calibration_metrics": (
                fixed_calibration_metrics
                if name == "calibrated_fixed"
                else adaptive_calibration_metrics
                if name == "adaptive_z_score"
                else rejection_metrics(
                    positive[positive_calibration],
                    relevant[positive_calibration],
                    negative[negative_calibration],
                    policy,
                )
            ),
            "evaluation_metrics": rejection_metrics(
                positive[positive_evaluation],
                relevant[positive_evaluation],
                negative[negative_evaluation],
                policy,
            ),
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
