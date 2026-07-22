"""Evaluate the controlled zero-shot tag vocabulary against the demo COCO labels."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from muselens.encoder import ClipEncoder
from muselens.repository import ImageRepository
from muselens.tags import ZeroShotTagger


SLUG_TO_COCO = {
    "person": "person",
    "dog": "dog",
    "cat": "cat",
    "bird": "bird",
    "elephant": "elephant",
    "cow": "cow",
    "horse": "horse",
    "sheep": "sheep",
    "giraffe": "giraffe",
    "car": "car",
    "bus": "bus",
    "airplane": "airplane",
    "bicycle": "bicycle",
    "motorcycle": "motorcycle",
    "boat": "boat",
    "pizza": "pizza",
    "cake": "cake",
    "sports-ball": "sports ball",
    "snowboard": "snowboard",
    "laptop": "laptop",
    "cell-phone": "cell phone",
    "book": "book",
    "clock": "clock",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=Path("demo_assets/state/index.sqlite3"))
    parser.add_argument("--manifest", type=Path, default=Path("demo_assets/manifest.json"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/evaluations/auto-tags-demo-v1.json"),
    )
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text())
    ground_truth = {
        item["original_filename"]: set(item["categories"]) for item in manifest["images"]
    }
    encoder = ClipEncoder(manifest["model_id"])
    tagger = ZeroShotTagger(encoder)
    repository = ImageRepository(args.database)
    repository.initialize()

    true_positive = false_positive = false_negative = image_hits = tagged_images = 0
    examples = []
    known_categories = set(SLUG_TO_COCO.values())
    for stored, vector in repository.iter_index(model_id=encoder.model_id):
        tags = tagger.predict(vector)
        if args.persist:
            repository.replace_tags(stored.image.image_id, tags, tagger.model_id)
        predicted = {SLUG_TO_COCO[tag.slug] for tag in tags if tag.slug in SLUG_TO_COCO}
        expected = ground_truth[stored.image.filename].intersection(known_categories)
        matches = predicted.intersection(expected)
        true_positive += len(matches)
        false_positive += len(predicted - expected)
        false_negative += len(expected - predicted)
        image_hits += bool(matches)
        tagged_images += bool(tags)
        examples.append(
            {
                "filename": stored.image.filename,
                "predicted": [
                    {"slug": tag.slug, "label": tag.label, "score": round(tag.score, 6)}
                    for tag in tags
                ],
                "expected_known_objects": sorted(expected),
                "matched_objects": sorted(matches),
            }
        )

    precision = true_positive / max(true_positive + false_positive, 1)
    recall = true_positive / max(true_positive + false_negative, 1)
    report = {
        "experiment": "zero-shot-controlled-auto-tags",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_id": encoder.model_id,
        "tagger_model_id": tagger.model_id,
        "protocol": {
            "images": len(examples),
            "vocabulary_size": len(tagger.definitions),
            "max_tags": tagger.max_tags,
            "min_score": tagger.min_score,
            "relative_margin": tagger.relative_margin,
            "ground_truth": "COCO categories restricted to exact controlled-vocabulary objects",
        },
        "metrics": {
            "tagged_images": tagged_images,
            "image_object_hit_rate": image_hits / max(len(examples), 1),
            "object_precision": precision,
            "object_recall": recall,
            "object_f1": 2 * precision * recall / max(precision + recall, 1e-12),
        },
        "persisted": args.persist,
        "examples": examples,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report["metrics"], ensure_ascii=False))
    print(f"report={args.output}")


if __name__ == "__main__":
    main()
