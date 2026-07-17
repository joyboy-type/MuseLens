#!/usr/bin/env python3
"""Safely re-encode the existing local image library with another model."""

import argparse
from pathlib import Path
import sys
from time import perf_counter


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from muselens.config import settings  # noqa: E402
from muselens.encoder import VisionLanguageEncoder  # noqa: E402
from muselens.index import VectorIndex  # noqa: E402
from muselens.library import ImageLibrary  # noqa: E402
from muselens.repository import ImageRepository  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Atomically rebuild stored image embeddings without deleting originals."
    )
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--batch-size", type=int, default=8)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.batch_size < 1:
        raise ValueError("--batch-size must be at least 1")

    repository = ImageRepository(settings.state_dir / "index.sqlite3")
    repository.initialize()
    encoder = VisionLanguageEncoder(args.model_id)
    library = ImageLibrary(
        settings.image_dir,
        repository,
        VectorIndex(),
        encoder,
        thumbnail_dir=settings.thumbnail_dir,
        thumbnail_max_size=settings.thumbnail_max_size,
        thumbnail_quality=settings.thumbnail_quality,
    )

    started = perf_counter()
    count = library.rebuild_embeddings(batch_size=args.batch_size)
    duration = perf_counter() - started
    print(f"model={args.model_id}")
    print(f"rebuilt_images={count}")
    print(f"duration_seconds={duration:.2f}")
    print("original_images_preserved=true")


if __name__ == "__main__":
    main()
