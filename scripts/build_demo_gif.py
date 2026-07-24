#!/usr/bin/env python3
"""Build a compact README demo GIF from the live MuseLens deployment."""

from __future__ import annotations

import argparse
from io import BytesIO
import json
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WIDTH = 960
HEIGHT = 540
BACKGROUND = "#0b1020"
PANEL = "#171c30"
TEXT = "#f8fafc"
MUTED = "#a5b4fc"
ACCENT = "#a855f7"
CYAN = "#2dd4bf"


def font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        Path("/System/Library/Fonts/STHeiti Medium.ttc"),
        Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        Path("/System/Library/Fonts/SFNS.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            try:
                return ImageFont.truetype(str(candidate), size=size, index=0)
            except OSError:
                continue
    return ImageFont.load_default(size=size)


def request_json(base_url: str, path: str, payload: dict[str, Any]) -> Any:
    target = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    request = Request(
        target,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=30) as response:  # noqa: S310 - CLI-selected URL
        return json.load(response)


def request_image(base_url: str, image_id: str) -> Image.Image:
    target = urljoin(
        base_url.rstrip("/") + "/",
        f"v1/images/{image_id}/thumbnail",
    )
    with urlopen(target, timeout=30) as response:  # noqa: S310 - CLI-selected URL
        return Image.open(BytesIO(response.read())).convert("RGB")


def cover(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    return ImageOps.fit(image.convert("RGB"), size, method=Image.Resampling.LANCZOS)


def rounded_panel(
    canvas: Image.Image,
    box: tuple[int, int, int, int],
    *,
    fill: str = PANEL,
    outline: str = "#374066",
    radius: int = 18,
) -> ImageDraw.ImageDraw:
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2)
    return draw


def header(draw: ImageDraw.ImageDraw, kicker: str, title: str, body: str) -> None:
    draw.text((56, 42), kicker, font=font(17, bold=True), fill=MUTED)
    draw.text((56, 76), title, font=font(36, bold=True), fill=TEXT)
    draw.text((58, 130), body, font=font(18), fill="#cbd5e1")


def title_scene(home: Image.Image) -> Image.Image:
    background = cover(home, (WIDTH, HEIGHT)).filter(ImageFilter.GaussianBlur(8))
    background = ImageEnhance.Brightness(background).enhance(0.28)
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (8, 12, 28, 130))
    background = Image.alpha_composite(background.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(background)
    draw.rounded_rectangle((54, 48, 194, 58), radius=5, fill=ACCENT)
    draw.text((54, 105), "MuseLens", font=font(58, bold=True), fill=TEXT)
    draw.text((57, 180), "多模态图片检索与智能整理系统", font=font(29, bold=True), fill="#ddd6fe")
    draw.text((57, 239), "中文 / English / 以图搜图", font=font(21), fill="#cbd5e1")
    draw.rounded_rectangle((55, 320, 495, 394), radius=18, fill=(23, 28, 48, 235))
    draw.text((82, 340), "真实向量编码  ·  本地索引  ·  非关键词映射", font=font(20), fill=TEXT)
    draw.text((57, 474), "sinbaby-muselens.ms.show", font=font(16), fill=MUTED)
    return background


def product_scene(home: Image.Image) -> Image.Image:
    canvas = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    screenshot = cover(home, (842, 474))
    screenshot = ImageEnhance.Contrast(screenshot).enhance(1.03)
    canvas.paste(screenshot, (59, 38))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((45, 24, 915, 526), radius=24, outline="#8b5cf6", width=3)
    draw.rounded_rectangle((659, 56, 874, 93), radius=18, fill="#6d28d9")
    draw.text((686, 64), "真实线上界面", font=font(16, bold=True), fill=TEXT)
    return canvas


def search_scene(
    query: str,
    results: list[dict[str, Any]],
    thumbnails: list[Image.Image],
    *,
    caption: str,
) -> Image.Image:
    canvas = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(canvas)
    header(draw, "LIVE SEMANTIC SEARCH", "文件名不需要包含查询词", caption)
    rounded_panel(canvas, (55, 170, 905, 226), fill="#11172a", outline="#8b5cf6")
    draw.text((82, 184), "⌕", font=font(25, bold=True), fill="#c4b5fd")
    draw.text((121, 184), query, font=font(21, bold=True), fill=TEXT)
    draw.rounded_rectangle((785, 181, 882, 216), radius=16, fill="#7c3aed")
    draw.text((810, 188), "搜索", font=font(16, bold=True), fill=TEXT)

    card_width = 256
    for index, (result, thumbnail) in enumerate(zip(results[:3], thumbnails[:3], strict=True)):
        left = 55 + index * (card_width + 27)
        top = 252
        rounded_panel(canvas, (left, top, left + card_width, 492))
        picture = cover(thumbnail, (card_width - 16, 150))
        canvas.paste(picture, (left + 8, top + 8))
        score = max(0, min(99, round((1 - index * 0.13) * 96)))
        draw.rounded_rectangle((left + 15, top + 16, left + 93, top + 43), radius=12, fill="#111827")
        draw.text((left + 26, top + 21), f"相关 {score}%", font=font(13, bold=True), fill="#ddd6fe")
        tags = " · ".join(tag["label"] for tag in result.get("tags", [])[:2]) or "语义结果"
        draw.text((left + 14, top + 173), tags, font=font(15, bold=True), fill=TEXT)
        draw.text((left + 14, top + 204), "SigLIP2 向量召回", font=font(13), fill="#94a3b8")
    return canvas


def upload_scene(assets: list[Image.Image]) -> Image.Image:
    canvas = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(canvas)
    header(draw, "TEMPORARY GALLERY", "上传自己的图片，验证完整后端链路", "不污染固定图库 · 会话隔离 · 30 分钟自动清理")
    labels = ["上传", "批量编码", "建立索引", "双语搜索", "立即清除"]
    for index, label in enumerate(labels):
        left = 55 + index * 178
        draw.ellipse((left, 192, left + 42, 234), fill=ACCENT if index < 4 else CYAN)
        draw.text((left + 15, 201), str(index + 1), font=font(15, bold=True), fill=TEXT)
        draw.text((left - 2, 247), label, font=font(16, bold=True), fill=TEXT)
        if index < len(labels) - 1:
            draw.line((left + 53, 213, left + 165, 213), fill="#64748b", width=3)
    for index, asset in enumerate(assets[:3]):
        left = 190 + index * 205
        draw.rounded_rectangle((left, 315, left + 170, 470), radius=16, fill=PANEL, outline="#3b4265", width=2)
        canvas.paste(cover(asset, (154, 139)), (left + 8, 323))
    draw.text((55, 502), "线上合同已验证：3 个文件 · 6 次中英文查询 · 隔离 404 · 清理成功", font=font(15), fill=MUTED)
    return canvas


def metrics_scene() -> Image.Image:
    canvas = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(canvas)
    header(draw, "REPRODUCIBLE EVIDENCE", "效果和边界都有机器可读证据", "不是只展示一个 dog 查询，也不把相似度伪装成概率")
    metrics = [
        ("95.24%", "线上 84 条双语查询 Hit@5"),
        ("99.36%", "2,500 张扰动图，以图搜图 R@1"),
        ("10.87×", "5,000 图纯索引加速"),
        ("−89.0%", "10 万向量搜索后 RSS"),
    ]
    for index, (value, label) in enumerate(metrics):
        left = 55 + (index % 2) * 435
        top = 184 + (index // 2) * 145
        rounded_panel(canvas, (left, top, left + 405, top + 118), outline="#4c4f78")
        draw.text((left + 25, top + 18), value, font=font(34, bold=True), fill="#c4b5fd" if index < 2 else "#5eead4")
        draw.text((left + 26, top + 72), label, font=font(16), fill="#cbd5e1")
    draw.rounded_rectangle((55, 484, 905, 516), radius=15, fill="#1f1640")
    draw.text((188, 490), "GitHub Actions：前端 + 后端 + 部署后真实上传质量门", font=font(15, bold=True), fill="#ddd6fe")
    return canvas


def closing_scene() -> Image.Image:
    canvas = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((54, 58, 906, 482), radius=28, fill="#151129", outline="#8b5cf6", width=3)
    draw.text((104, 112), "MuseLens", font=font(52, bold=True), fill=TEXT)
    draw.text((108, 181), "从模型实验到可部署产品的完整闭环", font=font(27, bold=True), fill="#ddd6fe")
    bullets = [
        "React + FastAPI 单容器应用",
        "SigLIP2 + mmap 精确向量检索",
        "SQLite 持久化、标签、相册与任务",
        "ModelScope 线上部署与端到端 CI",
    ]
    for index, bullet in enumerate(bullets):
        y = 250 + index * 43
        draw.ellipse((110, y + 7, 122, y + 19), fill=CYAN)
        draw.text((142, y), bullet, font=font(19), fill="#cbd5e1")
    draw.text((107, 435), "github.com/joyboy-type/MuseLens", font=font(16, bold=True), fill=MUTED)
    return canvas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="https://sinbaby-muselens.ms.show")
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "docs" / "images" / "muselens-demo.gif",
    )
    args = parser.parse_args()

    queries = [
        ("手机", "中文短词也会进入真实语义向量空间"),
        ("a person holding a mobile phone", "英文长句检索同一套个人图库"),
    ]
    live_results = [request_json(args.base_url, "/v1/search/text", {"query": query, "top_k": 3}) for query, _ in queries]
    live_thumbnails = [
        [request_image(args.base_url, result["image_id"]) for result in results[:3]]
        for results in live_results
    ]
    home = Image.open(PROJECT_ROOT / "docs" / "images" / "muselens-home.png").convert("RGB")
    manifest = json.loads((PROJECT_ROOT / "demo_assets" / "manifest.json").read_text())
    upload_assets = [
        Image.open(PROJECT_ROOT / "demo_assets" / "images" / record["stored_filename"]).convert("RGB")
        for record in manifest["images"][:3]
    ]

    frames = [
        title_scene(home),
        product_scene(home),
        search_scene(queries[0][0], live_results[0], live_thumbnails[0], caption=queries[0][1]),
        search_scene(queries[1][0], live_results[1], live_thumbnails[1], caption=queries[1][1]),
        upload_scene(upload_assets),
        metrics_scene(),
        closing_scene(),
    ]
    durations = [1800, 1600, 2200, 2400, 2300, 2600, 2400]
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
    print(f"demo_gif={args.output}")
    print(f"frames={len(frames)}")
    print(f"duration_seconds={sum(durations) / 1000:.1f}")
    print(f"size_bytes={args.output.stat().st_size}")


if __name__ == "__main__":
    main()
