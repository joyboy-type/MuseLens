#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import sys
from time import perf_counter

import numpy as np
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from muselens.config import settings  # noqa: E402
from muselens.adapters import DualEncoderAdapter  # noqa: E402
from muselens.encoder import ClipEncoder  # noqa: E402
from muselens.evaluation import retrieval_metrics  # noqa: E402
from muselens.index import normalize  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate text-to-image retrieval.")
    parser.add_argument(
        "--sample-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "evaluation" / "sample-v1",
    )
    parser.add_argument("--model-id", default=settings.clip_model_id)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument(
        "--adapter-checkpoint",
        type=Path,
        help="Optional frozen-feature adapter checkpoint produced by train_adapter.py.",
    )
    parser.add_argument(
        "--queries",
        type=Path,
        help="Optional bilingual JSONL query set; defaults to all Flickr captions.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "artifacts" / "evaluations" / "clip-vit-b32-sample-v1.json",
    )
    return parser.parse_args()


def read_manifest(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(
            f"Evaluation manifest not found at {path}. Run download_evaluation_sample.py first."
        )
    with path.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def read_bilingual_queries(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as file:
        records = [json.loads(line) for line in file if line.strip()]
    queries: list[dict] = []
    for record in records:
        for language in ("en", "zh"):
            queries.append(
                {
                    "image_id": record["image_id"],
                    "language": language,
                    "text": record[language],
                }
            )
    return queries


def batched(items: list, batch_size: int):
    for start in range(0, len(items), batch_size):
        yield items[start : start + batch_size]


def encode_images(
    encoder: ClipEncoder,
    image_paths: list[Path],
    batch_size: int,
) -> np.ndarray:
    vectors = []
    for batch_number, paths in enumerate(batched(image_paths, batch_size), start=1):
        images = []
        for path in paths:
            with Image.open(path) as image:
                images.append(image.convert("RGB"))
        vectors.append(encoder.encode_images(images))
        print(f"image_batch={batch_number} encoded={min(batch_number * batch_size, len(image_paths))}")
    return np.concatenate(vectors)


def encode_texts(encoder: ClipEncoder, texts: list[str], batch_size: int) -> np.ndarray:
    vectors = []
    for batch_number, batch in enumerate(batched(texts, batch_size), start=1):
        vectors.append(encoder.encode_texts(batch))
        print(f"text_batch={batch_number} encoded={min(batch_number * batch_size, len(texts))}")
    return np.concatenate(vectors)


def normalize_rows(matrix: np.ndarray) -> np.ndarray:
    return np.stack([normalize(row) for row in matrix])


def apply_adapter(
    image_vectors: np.ndarray,
    text_vectors: np.ndarray,
    checkpoint_path: Path,
    expected_model_id: str,
) -> tuple[np.ndarray, np.ndarray, dict]:
    import torch

    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    if checkpoint["model_id"] != expected_model_id:
        raise ValueError("adapter checkpoint model_id does not match --model-id")
    adapter = DualEncoderAdapter(
        embedding_dim=checkpoint["embedding_dim"],
        bottleneck_dim=checkpoint["bottleneck_dim"],
        dropout=0.0,
    )
    adapter.load_state_dict(checkpoint["state_dict"])
    adapter.eval()
    with torch.inference_mode():
        images = adapter.adapt_images(torch.from_numpy(image_vectors)).numpy()
        texts = adapter.adapt_texts(torch.from_numpy(text_vectors)).numpy()
    return images, texts, checkpoint


def main() -> None:
    args = parse_args()
    if args.batch_size < 1:
        raise ValueError("--batch-size must be at least 1")
    records = read_manifest(args.sample_dir / "manifest.jsonl")
    image_paths = [args.sample_dir / "images" / record["filename"] for record in records]
    image_position = {record["image_id"]: position for position, record in enumerate(records)}
    if args.queries:
        query_records = read_bilingual_queries(args.queries)
        captions = [record["text"] for record in query_records]
        languages = [record["language"] for record in query_records]
        relevant_image = np.array(
            [image_position[record["image_id"]] for record in query_records]
        )
    else:
        captions = [caption for record in records for caption in record["captions"]]
        languages = ["en"] * len(captions)
        relevant_image = np.repeat(np.arange(len(records)), 5)

    encoder = ClipEncoder(args.model_id)
    load_started = perf_counter()
    encoder.load()
    model_load_seconds = perf_counter() - load_started
    print(f"model={args.model_id} device={encoder.device} load_seconds={model_load_seconds:.2f}")

    image_started = perf_counter()
    image_vectors = normalize_rows(encode_images(encoder, image_paths, args.batch_size))
    image_seconds = perf_counter() - image_started

    text_started = perf_counter()
    text_vectors = normalize_rows(encode_texts(encoder, captions, args.batch_size * 2))
    text_seconds = perf_counter() - text_started

    adapter_metadata = None
    if args.adapter_checkpoint:
        image_vectors, text_vectors, checkpoint = apply_adapter(
            image_vectors,
            text_vectors,
            args.adapter_checkpoint,
            args.model_id,
        )
        adapter_metadata = {
            "checkpoint": str(args.adapter_checkpoint.resolve().relative_to(PROJECT_ROOT)),
            "epoch": checkpoint["epoch"],
            "validation": checkpoint["validation"],
        }

    similarities = text_vectors @ image_vectors.T
    metrics = retrieval_metrics(similarities, relevant_image)
    metrics_by_language = {
        language: retrieval_metrics(
            similarities[np.array(languages) == language],
            relevant_image[np.array(languages) == language],
        )
        for language in sorted(set(languages))
    }
    result = {
        "experiment": "zero-shot-text-to-image-retrieval",
        "model_id": args.model_id,
        "adapter": adapter_metadata,
        "device": str(encoder.device),
        "sample": str(args.sample_dir.relative_to(PROJECT_ROOT)),
        "query_set": (
            str(args.queries.resolve().relative_to(PROJECT_ROOT))
            if args.queries
            else "flickr8k-captions"
        ),
        "images": len(records),
        "queries": len(captions),
        "metrics": metrics,
        "metrics_by_language": metrics_by_language,
        "timing_seconds": {
            "model_load": model_load_seconds,
            "image_encoding_total": image_seconds,
            "image_encoding_per_item": image_seconds / len(records),
            "text_encoding_total": text_seconds,
            "text_encoding_per_query": text_seconds / len(captions),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"saved={args.output}")


if __name__ == "__main__":
    main()
