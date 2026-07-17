#!/usr/bin/env python3
"""Train lightweight retrieval adapters on frozen vision-language embeddings."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import random
import sys
from time import perf_counter

import numpy as np
from PIL import Image
import torch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from muselens.adapters import DualEncoderAdapter, symmetric_contrastive_loss  # noqa: E402
from muselens.config import settings  # noqa: E402
from muselens.encoder import VisionLanguageEncoder  # noqa: E402
from muselens.evaluation import retrieval_metrics  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train frozen-feature retrieval adapters.")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument(
        "--validation-data-dir",
        type=Path,
        help="Optional official validation split; otherwise split --data-dir by image.",
    )
    parser.add_argument("--model-id", default=settings.clip_model_id)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--image-batch-size", type=int, default=8)
    parser.add_argument("--text-batch-size", type=int, default=64)
    parser.add_argument("--bottleneck-dim", type=int, default=128)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-3)
    parser.add_argument("--validation-fraction", type=float, default=0.15)
    parser.add_argument("--patience", type=int, default=5)
    parser.add_argument("--seed", type=int, default=2026)
    return parser.parse_args()


def read_manifest(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def manifest_digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def batches(items: list, batch_size: int):
    for start in range(0, len(items), batch_size):
        yield items[start : start + batch_size]


def encode_features(
    encoder: VisionLanguageEncoder,
    records: list[dict],
    data_dir: Path,
    image_batch_size: int,
    text_batch_size: int,
) -> tuple[np.ndarray, np.ndarray]:
    image_vectors = []
    for paths in batches(
        [data_dir / "images" / record["filename"] for record in records],
        image_batch_size,
    ):
        images = []
        try:
            for path in paths:
                with Image.open(path) as opened:
                    images.append(opened.convert("RGB"))
            image_vectors.append(encoder.encode_images(images))
        finally:
            for image in images:
                image.close()

    captions = [caption for record in records for caption in record["captions"]]
    text_vectors = [
        encoder.encode_texts(batch) for batch in batches(captions, text_batch_size)
    ]
    images_array = np.concatenate(image_vectors).astype(np.float32)
    texts_array = np.concatenate(text_vectors).astype(np.float32)
    return images_array, texts_array.reshape(len(records), -1, images_array.shape[1])


def load_or_create_feature_cache(
    args: argparse.Namespace,
    records: list[dict],
    manifest_path: Path,
    data_dir: Path,
) -> tuple[np.ndarray, np.ndarray, Path]:
    digest = manifest_digest(manifest_path)
    cache_dir = PROJECT_ROOT / "artifacts" / "feature-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    safe_model = args.model_id.replace("/", "--")
    cache_path = cache_dir / f"{safe_model}-{digest[:12]}.npz"
    if cache_path.exists():
        cached = np.load(cache_path)
        return cached["image_features"], cached["text_features"], cache_path

    encoder = VisionLanguageEncoder(args.model_id)
    images, texts = encode_features(
        encoder,
        records,
        data_dir,
        args.image_batch_size,
        args.text_batch_size,
    )
    np.savez_compressed(
        cache_path,
        image_features=images,
        text_features=texts,
        model_id=np.array(args.model_id),
        manifest_sha256=np.array(digest),
    )
    return images, texts, cache_path


def split_indices(count: int, validation_fraction: float, seed: int) -> tuple[list[int], list[int]]:
    if count < 3:
        raise ValueError("training requires at least three distinct images")
    if not 0 < validation_fraction < 0.5:
        raise ValueError("--validation-fraction must be between 0 and 0.5")
    indices = list(range(count))
    random.Random(seed).shuffle(indices)
    validation_count = max(1, round(count * validation_fraction))
    return indices[validation_count:], indices[:validation_count]


def evaluate(
    model: DualEncoderAdapter,
    image_features: torch.Tensor,
    text_features: torch.Tensor,
) -> dict[str, float]:
    model.eval()
    with torch.inference_mode():
        images = model.adapt_images(image_features)
        flattened_text = text_features.reshape(-1, text_features.shape[-1])
        texts = model.adapt_texts(flattened_text)
        similarities = (texts @ images.T).cpu().numpy()
    relevant = np.repeat(np.arange(image_features.shape[0]), text_features.shape[1])
    return retrieval_metrics(similarities, relevant)


def main() -> None:
    args = parse_args()
    if args.epochs < 1 or args.batch_size < 2 or args.patience < 1:
        raise ValueError("epochs must be positive and batch size must be at least two")
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    manifest_path = args.data_dir / "manifest.jsonl"
    records = read_manifest(manifest_path)
    started = perf_counter()
    image_array, text_array, cache_path = load_or_create_feature_cache(
        args, records, manifest_path, args.data_dir
    )
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    images = torch.from_numpy(image_array).to(device)
    texts = torch.from_numpy(text_array).to(device)

    validation_cache_path = cache_path
    if args.validation_data_dir:
        validation_manifest = args.validation_data_dir / "manifest.jsonl"
        validation_records = read_manifest(validation_manifest)
        validation_image_array, validation_text_array, validation_cache_path = (
            load_or_create_feature_cache(
                args,
                validation_records,
                validation_manifest,
                args.validation_data_dir,
            )
        )
        train_indices = list(range(len(records)))
        validation_images = torch.from_numpy(validation_image_array).to(device)
        validation_texts = torch.from_numpy(validation_text_array).to(device)
    else:
        train_indices, validation_indices = split_indices(
            len(records), args.validation_fraction, args.seed
        )
        validation_records = [records[index] for index in validation_indices]
        validation_images = images[validation_indices]
        validation_texts = texts[validation_indices]

    model = DualEncoderAdapter(
        embedding_dim=images.shape[1],
        bottleneck_dim=args.bottleneck_dim,
    ).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=args.learning_rate,
        weight_decay=args.weight_decay,
    )

    baseline = evaluate(model, validation_images, validation_texts)
    history: list[dict] = []
    best_mrr = -1.0
    epochs_without_improvement = 0
    args.output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = args.output_dir / "best.pt"

    train_index_tensor = torch.tensor(train_indices, device=device)
    for epoch in range(1, args.epochs + 1):
        model.train()
        order = train_index_tensor[torch.randperm(len(train_indices), device=device)]
        total_loss = 0.0
        batch_count = 0
        for start in range(0, len(order), args.batch_size):
            selected = order[start : start + args.batch_size]
            if len(selected) < 2:
                continue
            caption_choices = torch.randint(
                text_array.shape[1],
                (len(selected),),
                device=device,
            )
            image_batch = images[selected]
            text_batch = texts[selected, caption_choices]
            adapted_images, adapted_texts = model(image_batch, text_batch)
            loss = symmetric_contrastive_loss(
                adapted_images,
                adapted_texts,
                model.logit_scale,
            )
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            total_loss += float(loss.detach().cpu())
            batch_count += 1

        metrics = evaluate(model, validation_images, validation_texts)
        record = {
            "epoch": epoch,
            "train_loss": total_loss / max(batch_count, 1),
            "validation": metrics,
        }
        history.append(record)
        print(json.dumps(record, ensure_ascii=False))
        if metrics["mrr"] > best_mrr:
            best_mrr = metrics["mrr"]
            epochs_without_improvement = 0
            torch.save(
                {
                    "state_dict": model.state_dict(),
                    "model_id": args.model_id,
                    "embedding_dim": images.shape[1],
                    "bottleneck_dim": args.bottleneck_dim,
                    "seed": args.seed,
                    "epoch": epoch,
                    "validation": metrics,
                },
                checkpoint_path,
            )
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= args.patience:
                print(f"early_stopping_epoch={epoch} patience={args.patience}")
                break

    result = {
        "experiment": "frozen-siglip2-dual-adapter",
        "model_id": args.model_id,
        "device": str(device),
        "data_dir": str(args.data_dir.resolve().relative_to(PROJECT_ROOT)),
        "images": len(records) + len(validation_records),
        "train_images": len(train_indices),
        "validation_images": len(validation_records),
        "captions_per_image": text_array.shape[1],
        "trainable_parameters": sum(parameter.numel() for parameter in model.parameters()),
        "baseline_validation": baseline,
        "best_validation_mrr": best_mrr,
        "feature_cache": {
            "train": str(cache_path.relative_to(PROJECT_ROOT)),
            "validation": str(validation_cache_path.relative_to(PROJECT_ROOT)),
        },
        "checkpoint": str(checkpoint_path.resolve().relative_to(PROJECT_ROOT)),
        "duration_seconds": perf_counter() - started,
        "config": vars(args) | {"data_dir": str(args.data_dir), "output_dir": str(args.output_dir)},
        "history": history,
    }
    (args.output_dir / "training_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {key: value for key, value in result.items() if key != "history"},
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
