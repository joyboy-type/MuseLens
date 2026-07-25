#!/usr/bin/env python3
"""Build compact GitHub/social launch covers for MuseLens."""

from __future__ import annotations

import argparse
import base64
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WIDTH = 1200
HEIGHT = 630
INK = "#f4f7ef"
MUTED = "#a8afa4"
LIME = "#d7ff52"
PANEL = "#111512"


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


def prepare_screenshot(source: Path) -> Image.Image:
    image = Image.open(source).convert("RGB")
    return ImageOps.fit(
        image,
        (630, 414),
        method=Image.Resampling.LANCZOS,
        centering=(0.45, 0.38),
    )


def rounded_screenshot(image: Image.Image, radius: int = 22) -> Image.Image:
    mask = Image.new("L", image.size)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, image.width - 1, image.height - 1),
        radius=radius,
        fill=255,
    )
    result = image.convert("RGBA")
    result.putalpha(mask)
    return result


def build_png(screenshot: Image.Image, output: Path) -> None:
    canvas = Image.new("RGB", (WIDTH, HEIGHT), "#090b09")

    glow = Image.new("RGBA", (WIDTH, HEIGHT))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((760, -210, 1330, 360), fill=(178, 255, 64, 48))
    glow_draw.ellipse((-260, 440, 300, 890), fill=(87, 114, 255, 26))
    glow = glow.filter(ImageFilter.GaussianBlur(75))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), glow)

    grid = Image.new("RGBA", (WIDTH, HEIGHT))
    grid_draw = ImageDraw.Draw(grid)
    for x in range(0, WIDTH, 42):
        grid_draw.line((x, 0, x, HEIGHT), fill=(255, 255, 255, 8), width=1)
    for y in range(0, HEIGHT, 42):
        grid_draw.line((0, y, WIDTH, y), fill=(255, 255, 255, 8), width=1)
    canvas = Image.alpha_composite(canvas, grid)

    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((58, 49, 100, 91), radius=11, fill=LIME)
    draw.ellipse((69, 60, 79, 70), outline="#101510", width=2)
    draw.line((78, 69, 89, 80), fill="#101510", width=3)
    draw.text((116, 52), "MuseLens", font=font(31, bold=True), fill=INK)
    draw.text((118, 87), "MULTIMODAL PHOTO SEARCH", font=font(12, bold=True), fill=LIME)

    draw.text((58, 161), "Search photos", font=font(62, bold=True), fill=INK)
    draw.text((58, 226), "by meaning.", font=font(62, bold=True), fill=LIME)
    draw.text((61, 317), "多模态图片检索与个人图库", font=font(23, bold=True), fill="#d8ddd5")
    draw.text((61, 360), "中文 · English · Image-to-Image", font=font(18), fill=MUTED)

    badges = [
        ("95.24%", "Live Hit@5"),
        ("99.36%", "Image R@1"),
    ]
    for index, (value, label) in enumerate(badges):
        left = 58 + index * 190
        draw.rounded_rectangle(
            (left, 430, left + 170, 504),
            radius=17,
            fill="#121712",
            outline="#293128",
            width=2,
        )
        draw.text((left + 17, 443), value, font=font(24, bold=True), fill=LIME)
        draw.text((left + 18, 477), label, font=font(13, bold=True), fill=MUTED)

    draw.text(
        (59, 550),
        "React  ·  FastAPI  ·  SigLIP2  ·  SQLite",
        font=font(15, bold=True),
        fill="#d5dbd2",
    )
    draw.text((59, 580), "github.com/joyboy-type/MuseLens", font=font(14), fill=MUTED)

    shadow = Image.new("RGBA", canvas.size)
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle((506, 113, 1165, 557), radius=28, fill=(0, 0, 0, 165))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    canvas = Image.alpha_composite(canvas, shadow)

    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        (489, 91, 1149, 535),
        radius=27,
        fill=PANEL,
        outline="#394438",
        width=2,
    )
    draw.ellipse((520, 111, 530, 121), fill="#ff605c")
    draw.ellipse((538, 111, 548, 121), fill="#ffbd44")
    draw.ellipse((556, 111, 566, 121), fill="#00ca4e")
    draw.rounded_rectangle((585, 106, 967, 127), radius=10, fill="#202520")
    draw.text((702, 109), "sinbaby-muselens.ms.show", font=font(10), fill="#8f978d")

    framed = rounded_screenshot(screenshot, radius=18)
    canvas.alpha_composite(framed, (504, 141))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        (504, 141, 1134, 555),
        radius=18,
        outline="#454d43",
        width=2,
    )
    draw.rounded_rectangle((938, 489, 1115, 523), radius=15, fill="#d7ff52")
    draw.text((958, 497), "LIVE DEMO  ↗", font=font(14, bold=True), fill="#101510")

    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output, optimize=True, compress_level=9)


def build_svg(screenshot: Image.Image, output: Path) -> None:
    encoded = BytesIO()
    screenshot.save(encoded, format="JPEG", quality=73, optimize=True)
    screenshot_uri = base64.b64encode(encoded.getvalue()).decode()
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
  <defs>
    <radialGradient id="glow" cx="88%" cy="10%" r="62%">
      <stop offset="0" stop-color="#b9ff42" stop-opacity=".22"/>
      <stop offset=".55" stop-color="#0a0d0a" stop-opacity="0"/>
    </radialGradient>
    <pattern id="grid" width="42" height="42" patternUnits="userSpaceOnUse">
      <path d="M42 0H0V42" fill="none" stroke="#fff" stroke-opacity=".035"/>
    </pattern>
    <clipPath id="shot"><rect x="504" y="141" width="630" height="414" rx="18"/></clipPath>
    <filter id="shadow" x="-30%" y="-30%" width="160%" height="160%">
      <feDropShadow dx="0" dy="18" stdDeviation="16" flood-color="#000" flood-opacity=".7"/>
    </filter>
  </defs>
  <rect width="1200" height="630" fill="#090b09"/>
  <rect width="1200" height="630" fill="url(#glow)"/>
  <rect width="1200" height="630" fill="url(#grid)"/>
  <g font-family="Inter, Arial, 'PingFang SC', sans-serif">
    <rect x="58" y="49" width="42" height="42" rx="11" fill="#d7ff52"/>
    <circle cx="74" cy="65" r="5" fill="none" stroke="#101510" stroke-width="2"/>
    <path d="m78 69 11 11" stroke="#101510" stroke-width="3"/>
    <text x="116" y="80" fill="#f4f7ef" font-size="31" font-weight="700">MuseLens</text>
    <text x="118" y="104" fill="#d7ff52" font-size="12" font-weight="700" letter-spacing="1.4">MULTIMODAL PHOTO SEARCH</text>
    <text x="58" y="213" fill="#f4f7ef" font-size="62" font-weight="750">Search photos</text>
    <text x="58" y="278" fill="#d7ff52" font-size="62" font-weight="750">by meaning.</text>
    <text x="61" y="341" fill="#d8ddd5" font-size="23" font-weight="650">多模态图片检索与个人图库</text>
    <text x="61" y="382" fill="#a8afa4" font-size="18">中文 · English · Image-to-Image</text>
    <g>
      <rect x="58" y="430" width="170" height="74" rx="17" fill="#121712" stroke="#293128" stroke-width="2"/>
      <text x="75" y="469" fill="#d7ff52" font-size="24" font-weight="750">95.24%</text>
      <text x="76" y="491" fill="#a8afa4" font-size="13" font-weight="650">Live Hit@5</text>
      <rect x="248" y="430" width="170" height="74" rx="17" fill="#121712" stroke="#293128" stroke-width="2"/>
      <text x="265" y="469" fill="#d7ff52" font-size="24" font-weight="750">99.36%</text>
      <text x="266" y="491" fill="#a8afa4" font-size="13" font-weight="650">Image R@1</text>
    </g>
    <text x="59" y="566" fill="#d5dbd2" font-size="15" font-weight="650">React  ·  FastAPI  ·  SigLIP2  ·  SQLite</text>
    <text x="59" y="595" fill="#a8afa4" font-size="14">github.com/joyboy-type/MuseLens</text>
    <g filter="url(#shadow)">
      <rect x="489" y="91" width="660" height="464" rx="27" fill="#111512" stroke="#394438" stroke-width="2"/>
      <circle cx="525" cy="116" r="5" fill="#ff605c"/>
      <circle cx="543" cy="116" r="5" fill="#ffbd44"/>
      <circle cx="561" cy="116" r="5" fill="#00ca4e"/>
      <rect x="585" y="106" width="382" height="21" rx="10" fill="#202520"/>
      <text x="702" y="121" fill="#8f978d" font-size="10">sinbaby-muselens.ms.show</text>
      <image x="504" y="141" width="630" height="414" href="data:image/jpeg;base64,{screenshot_uri}" clip-path="url(#shot)" preserveAspectRatio="xMidYMid slice"/>
      <rect x="504" y="141" width="630" height="414" rx="18" fill="none" stroke="#454d43" stroke-width="2"/>
      <rect x="938" y="489" width="177" height="34" rx="15" fill="#d7ff52"/>
      <text x="958" y="511" fill="#101510" font-size="14" font-weight="750">LIVE DEMO ↗</text>
    </g>
  </g>
</svg>
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(svg)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--screenshot",
        type=Path,
        default=PROJECT_ROOT / "docs" / "images" / "muselens-home.png",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "docs" / "assets" / "launch",
    )
    args = parser.parse_args()

    screenshot = prepare_screenshot(args.screenshot)
    png_path = args.output_dir / "muselens-social-preview.png"
    svg_path = args.output_dir / "muselens-social-preview.svg"
    build_png(screenshot, png_path)
    build_svg(screenshot, svg_path)
    print(f"cover_png={png_path} size_bytes={png_path.stat().st_size}")
    print(f"cover_svg={svg_path} size_bytes={svg_path.stat().st_size}")


if __name__ == "__main__":
    main()
