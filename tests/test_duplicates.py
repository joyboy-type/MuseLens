from io import BytesIO
import random

from PIL import Image, ImageDraw

from muselens.duplicates import (
    VisualFingerprint,
    color_distance,
    duplicate_components,
    hash_distance,
    visual_fingerprint,
)


def patterned_image() -> Image.Image:
    image = Image.new("RGB", (180, 120), (220, 190, 120))
    draw = ImageDraw.Draw(image)
    draw.rectangle((12, 15, 84, 105), fill=(32, 75, 135))
    draw.ellipse((92, 20, 164, 92), fill=(210, 55, 60))
    draw.line((0, 119, 179, 0), fill=(245, 245, 230), width=7)
    return image


def jpeg_round_trip(image: Image.Image, quality: int = 42) -> Image.Image:
    buffer = BytesIO()
    image.resize((96, 64), Image.Resampling.LANCZOS).save(
        buffer,
        format="JPEG",
        quality=quality,
    )
    buffer.seek(0)
    with Image.open(buffer) as opened:
        return opened.convert("RGB")


def test_visual_fingerprint_survives_resize_and_jpeg_compression() -> None:
    original = visual_fingerprint(patterned_image())
    transformed = visual_fingerprint(jpeg_round_trip(patterned_image()))

    assert hash_distance(original.perceptual_hash, transformed.perceptual_hash) <= 8
    assert color_distance(original.average_color, transformed.average_color) <= 12


def test_color_guard_separates_flat_images_with_identical_structure() -> None:
    red = visual_fingerprint(Image.new("RGB", (80, 80), "red"))
    blue = visual_fingerprint(Image.new("RGB", (80, 80), "blue"))

    assert hash_distance(red.perceptual_hash, blue.perceptual_hash) == 0
    assert duplicate_components([red, blue], max_color_distance=45) == []


def test_duplicate_components_merge_an_edit_chain() -> None:
    fingerprints = [
        VisualFingerprint("0000000000000000", "808080"),
        VisualFingerprint("000000000000000f", "818181"),
        VisualFingerprint("00000000000000ff", "828282"),
        VisualFingerprint("ffffffffffffffff", "808080"),
    ]

    groups = duplicate_components(fingerprints, max_hash_distance=4)

    assert groups == [[0, 1, 2]]


def test_multi_index_candidate_blocks_match_brute_force_components() -> None:
    randomizer = random.Random(19)
    values = [randomizer.getrandbits(64) for _ in range(80)]
    values.extend(value ^ 0b1010101 for value in values[:12])
    fingerprints = [
        VisualFingerprint(f"{value:016x}", "8090a0")
        for value in values
    ]

    optimized = duplicate_components(fingerprints, max_hash_distance=4)
    adjacency = {position: set() for position in range(len(values))}
    for left in range(len(values)):
        for right in range(left):
            if (values[left] ^ values[right]).bit_count() <= 4:
                adjacency[left].add(right)
                adjacency[right].add(left)
    expected = []
    unseen = set(range(len(values)))
    while unseen:
        start = unseen.pop()
        component = {start}
        pending = [start]
        while pending:
            current = pending.pop()
            neighbors = adjacency[current] & unseen
            unseen.difference_update(neighbors)
            component.update(neighbors)
            pending.extend(neighbors)
        if len(component) > 1:
            expected.append(sorted(component))

    assert sorted(optimized) == sorted(expected)
