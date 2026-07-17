"""Run a fast, human-readable semantic-search contract test on Flickr8k images."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

from muselens.encoder import ClipEncoder
from muselens.index import IndexedImage, VectorIndex, filter_relevant_hits


CORPUS = [
    "1084040636_97d9633581.jpg",  # white dog
    "106490881_5a2dd9b7bd.jpg",  # child on a beach
    "1082379191_ec1e53f996.jpg",  # people on a dock
    "113678030_87a6a6e42e.jpg",  # snowboarder
    "114051287_dd85625a04.jpg",  # child leaving a car
    "1107246521_d16a476380.jpg",  # black dog
    "1167669558_87a8a467d6.jpg",  # yellow shirt
    "1174629344_a2e1a2bdbf.jpg",  # city crowd
]

CASES = [
    ("dog", {"1084040636_97d9633581.jpg", "1107246521_d16a476380.jpg"}),
    ("beach", {"106490881_5a2dd9b7bd.jpg"}),
    ("snow", {"113678030_87a6a6e42e.jpg"}),
    ("car", {"114051287_dd85625a04.jpg"}),
    ("yellow shirt", {"1167669558_87a8a467d6.jpg"}),
    ("crowd", {"1174629344_a2e1a2bdbf.jpg"}),
    ("狗", {"1084040636_97d9633581.jpg", "1107246521_d16a476380.jpg"}),
    ("海滩", {"106490881_5a2dd9b7bd.jpg"}),
    ("雪地", {"113678030_87a6a6e42e.jpg"}),
    ("汽车", {"114051287_dd85625a04.jpg"}),
    ("黄色衣服", {"1167669558_87a8a467d6.jpg"}),
    ("人群", {"1174629344_a2e1a2bdbf.jpg"}),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--images",
        type=Path,
        default=Path("data/evaluation/sample-v1/images"),
    )
    parser.add_argument(
        "--model",
        default="google/siglip2-base-patch16-224",
    )
    parser.add_argument("--relative-margin", type=float, default=0.035)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    missing = [filename for filename in CORPUS if not (args.images / filename).is_file()]
    if missing:
        raise SystemExit(f"Missing evaluation images: {', '.join(missing)}")

    encoder = ClipEncoder(args.model)
    index = VectorIndex()
    images: list[Image.Image] = []
    try:
        for filename in CORPUS:
            with Image.open(args.images / filename) as opened:
                images.append(opened.convert("RGB"))
        vectors = encoder.encode_images(images)
    finally:
        for image in images:
            image.close()

    for filename, vector in zip(CORPUS, vectors, strict=True):
        index.add(IndexedImage(filename, filename, "image/jpeg"), vector)

    query_vectors = encoder.encode_texts([query for query, _expected in CASES])
    results = []
    for (query, expected), vector in zip(CASES, query_vectors, strict=True):
        hits = filter_relevant_hits(
            index.search(vector, top_k=5),
            absolute_floor=None,
            relative_margin=args.relative_margin,
            max_results=5,
        )
        top = hits[0] if hits else None
        results.append(
            {
                "query": query,
                "top1": top.image.filename if top else None,
                "top1_score": top.score if top else None,
                "returned": len(hits),
                "passed": top is not None and top.image.filename in expected,
            }
        )

    passed = sum(result["passed"] for result in results)
    print(
        json.dumps(
            {
                "model": args.model,
                "corpus_size": len(CORPUS),
                "queries": len(CASES),
                "top1_passed": passed,
                "top1_accuracy": passed / len(CASES),
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if passed != len(CASES):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
