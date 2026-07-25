#!/usr/bin/env python3
"""Build the compact launch-edition MuseLens demo GIF from live API results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

import build_demo_gif as demo


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="https://sinbaby-muselens.ms.show")
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "docs" / "assets" / "launch" / "muselens-demo.gif",
    )
    args = parser.parse_args()

    # Match the current MuseLens product UI and social cover.
    demo.BACKGROUND = "#090b09"
    demo.PANEL = "#121712"
    demo.TEXT = "#f4f7ef"
    demo.MUTED = "#d7ff52"
    demo.ACCENT = "#8ca82d"
    demo.CYAN = "#d7ff52"

    queries = [
        ("手机", "中文短词也会进入真实语义向量空间"),
        ("a person holding a mobile phone", "英文长句检索同一套个人图库"),
    ]
    live_results = [
        demo.request_json(
            args.base_url,
            "/v1/search/text",
            {"query": query, "top_k": 3},
        )
        for query, _ in queries
    ]
    live_thumbnails = [
        [
            demo.request_image(args.base_url, result["image_id"])
            for result in results[:3]
        ]
        for results in live_results
    ]
    home = Image.open(
        PROJECT_ROOT / "docs" / "images" / "muselens-home.png"
    ).convert("RGB")
    manifest = json.loads(
        (PROJECT_ROOT / "demo_assets" / "manifest.json").read_text()
    )
    upload_assets = [
        Image.open(
            PROJECT_ROOT
            / "demo_assets"
            / "images"
            / record["stored_filename"]
        ).convert("RGB")
        for record in manifest["images"][:3]
    ]

    frames = [
        demo.title_scene(home),
        demo.product_scene(home),
        demo.search_scene(
            queries[0][0],
            live_results[0],
            live_thumbnails[0],
            caption=queries[0][1],
        ),
        demo.search_scene(
            queries[1][0],
            live_results[1],
            live_thumbnails[1],
            caption=queries[1][1],
        ),
        demo.upload_scene(upload_assets),
        demo.metrics_scene(),
        demo.closing_scene(),
    ]
    durations = [1500, 1400, 2000, 2200, 2100, 2300, 2100]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        args.output,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
        disposal=2,
    )
    print(f"launch_demo_gif={args.output}")
    print(f"frames={len(frames)}")
    print(f"duration_seconds={sum(durations) / 1000:.1f}")
    print(f"size_bytes={args.output.stat().st_size}")


if __name__ == "__main__":
    main()
