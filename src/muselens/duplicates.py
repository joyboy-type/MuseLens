from dataclasses import dataclass
from functools import lru_cache
from math import sqrt

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class VisualFingerprint:
    perceptual_hash: str
    average_color: str


@lru_cache(maxsize=1)
def _dct_matrix(size: int = 32) -> np.ndarray:
    positions = np.arange(size, dtype=np.float32)
    frequencies = positions.reshape(-1, 1)
    matrix = np.cos(np.pi * (2 * positions + 1) * frequencies / (2 * size))
    matrix[0] *= 1 / np.sqrt(size)
    matrix[1:] *= np.sqrt(2 / size)
    return matrix.astype(np.float32)


def visual_fingerprint(image: Image.Image) -> VisualFingerprint:
    """Return a resize/compression-tolerant pHash plus a color false-positive guard."""
    grayscale = image.convert("L").resize((32, 32), Image.Resampling.LANCZOS)
    pixels = np.asarray(grayscale, dtype=np.float32)
    transform = _dct_matrix()
    low_frequency = (transform @ pixels @ transform.T)[:8, :8]
    low_frequency[np.abs(low_frequency) < 1e-3] = 0
    median = float(np.median(low_frequency.reshape(-1)[1:]))
    bits = (low_frequency > median).reshape(-1)
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)

    rgb = np.asarray(
        image.convert("RGB").resize((1, 1), Image.Resampling.BOX),
        dtype=np.uint8,
    ).reshape(3)
    return VisualFingerprint(
        perceptual_hash=f"{value:016x}",
        average_color="".join(f"{int(channel):02x}" for channel in rgb),
    )


def hash_distance(left: str, right: str) -> int:
    if len(left) != 16 or len(right) != 16:
        raise ValueError("Perceptual hashes must be 64-bit hexadecimal strings.")
    return (int(left, 16) ^ int(right, 16)).bit_count()


def color_distance(left: str, right: str) -> float:
    if len(left) != 6 or len(right) != 6:
        raise ValueError("Average colors must be six-digit hexadecimal strings.")
    left_rgb = tuple(int(left[index : index + 2], 16) for index in (0, 2, 4))
    right_rgb = tuple(int(right[index : index + 2], 16) for index in (0, 2, 4))
    left_norm = sqrt(sum(channel**2 for channel in left_rgb))
    right_norm = sqrt(sum(channel**2 for channel in right_rgb))
    if left_norm < 1 or right_norm < 1:
        return sqrt(sum((first - second) ** 2 for first, second in zip(left_rgb, right_rgb)))
    # Compare chromatic direction instead of absolute brightness so exposure edits
    # remain duplicates while differently colored flat images stay separated.
    return 255 * sqrt(
        sum(
            (first / left_norm - second / right_norm) ** 2
            for first, second in zip(left_rgb, right_rgb)
        )
    )


def duplicate_components(
    fingerprints: list[VisualFingerprint],
    *,
    max_hash_distance: int = 8,
    max_color_distance: float = 45,
) -> list[list[int]]:
    """Group fingerprints connected by strict near-duplicate pair matches."""
    if max_hash_distance < 0 or max_hash_distance > 64:
        raise ValueError("max_hash_distance must be between 0 and 64.")
    if max_color_distance < 0:
        raise ValueError("max_color_distance must be non-negative.")

    parents = list(range(len(fingerprints)))

    def find(position: int) -> int:
        while parents[position] != position:
            parents[position] = parents[parents[position]]
            position = parents[position]
        return position

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    # Split the hash into distance+1 blocks. By the pigeonhole principle, two
    # 64-bit hashes within the configured radius must share at least one block.
    # This produces an exact candidate set without an O(n²) full scan.
    block_count = min(64, max_hash_distance + 1)
    base_width, wider_blocks = divmod(64, block_count)
    blocks: list[tuple[int, int]] = []
    shift = 0
    for block_index in range(block_count):
        width = base_width + int(block_index < wider_blocks)
        blocks.append((shift, (1 << width) - 1))
        shift += width
    buckets: dict[tuple[int, int], list[int]] = {}
    hash_values: list[int | None] = [None] * len(fingerprints)

    for position, fingerprint in enumerate(fingerprints):
        if not fingerprint.perceptual_hash or not fingerprint.average_color:
            continue
        value = int(fingerprint.perceptual_hash, 16)
        candidates: set[int] = set()
        for block_index, (block_shift, mask) in enumerate(blocks):
            candidates.update(buckets.get((block_index, (value >> block_shift) & mask), ()))
        if max_hash_distance == 64:
            candidates.update(range(position))
        for match in candidates:
            match_value = hash_values[match]
            if match_value is None or (value ^ match_value).bit_count() > max_hash_distance:
                continue
            if (
                color_distance(
                    fingerprint.average_color,
                    fingerprints[match].average_color,
                )
                <= max_color_distance
            ):
                union(position, match)
        hash_values[position] = value
        for block_index, (block_shift, mask) in enumerate(blocks):
            buckets.setdefault((block_index, (value >> block_shift) & mask), []).append(position)

    grouped: dict[int, list[int]] = {}
    for position in range(len(fingerprints)):
        grouped.setdefault(find(position), []).append(position)
    return [members for members in grouped.values() if len(members) > 1]
