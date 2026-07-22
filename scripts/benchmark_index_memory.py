"""Measure resident memory for exact NumPy and disk-backed mmap indexes."""

import argparse
import gc
import os
from pathlib import Path
import subprocess
import tempfile
import time

import numpy as np

from muselens.index import IndexedImage, MmapVectorIndex, VectorIndex


def resident_mb() -> float:
    output = subprocess.check_output(
        ["ps", "-o", "rss=", "-p", str(os.getpid())],
        text=True,
    )
    return int(output.strip()) / 1024


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("numpy", "mmap"), required=True)
    parser.add_argument("--count", type=int, default=100_000)
    parser.add_argument("--dimension", type=int, default=768)
    args = parser.parse_args()
    if args.count < 1 or args.dimension < 1:
        raise ValueError("count and dimension must be positive")

    with tempfile.TemporaryDirectory(prefix="muselens-index-memory-") as temporary:
        if args.backend == "numpy":
            index = VectorIndex()
        else:
            index = MmapVectorIndex(Path(temporary) / "vectors.f32")

        rng = np.random.default_rng(2026)
        vector = rng.normal(size=args.dimension).astype(np.float32)
        baseline_mb = resident_mb()
        started = time.perf_counter()
        for position in range(args.count):
            index.add(
                IndexedImage(str(position), f"{position}.jpg", "image/jpeg"),
                vector,
            )
        gc.collect()
        built_mb = resident_mb()
        build_seconds = time.perf_counter() - started

        started = time.perf_counter()
        hits = index.search(vector, 10)
        search_ms = (time.perf_counter() - started) * 1000
        gc.collect()
        searched_mb = resident_mb()
        cache_mb = (
            index.storage_path.stat().st_size / 2**20 if isinstance(index, MmapVectorIndex) else 0
        )
        print(f"backend={args.backend}")
        print(f"vectors={args.count} dimension={args.dimension}")
        print(f"baseline_rss_mb={baseline_mb:.1f}")
        print(f"built_rss_mb={built_mb:.1f}")
        print(f"searched_rss_mb={searched_mb:.1f}")
        print(f"build_seconds={build_seconds:.3f}")
        print(f"first_search_ms={search_ms:.3f}")
        print(f"cache_file_mb={cache_mb:.1f}")
        print(f"returned_hits={len(hits)}")
        close = getattr(index, "close", None)
        if close:
            close()


if __name__ == "__main__":
    main()
