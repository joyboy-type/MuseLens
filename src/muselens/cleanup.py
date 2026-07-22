from dataclasses import dataclass
from pathlib import Path
import shutil


REGENERABLE_PATHS = (
    Path("data/.download-cache"),
    Path("data/benchmarks"),
    Path("data/training"),
    Path("data/evaluation/coco-val2017"),
    Path("data/evaluation/image-retrieval-coco500-v1"),
)
FEATURE_CACHE_PATH = Path("artifacts/feature-cache")


@dataclass(frozen=True)
class CleanupEntry:
    path: Path
    size_bytes: int


def directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file() or path.is_symlink():
        return path.lstat().st_size
    return sum(
        item.lstat().st_size for item in path.rglob("*") if item.is_file() or item.is_symlink()
    )


def cleanup_entries(
    project_root: Path,
    *,
    include_feature_cache: bool = False,
) -> list[CleanupEntry]:
    root = project_root.resolve()
    candidates = list(REGENERABLE_PATHS)
    if include_feature_cache:
        candidates.append(FEATURE_CACHE_PATH)
    entries = []
    for relative in candidates:
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            raise ValueError(f"Refusing to inspect a path outside the project: {path}")
        if path.exists():
            entries.append(CleanupEntry(path, directory_size(path)))
    return entries


def remove_entry(entry: CleanupEntry, project_root: Path) -> None:
    root = project_root.resolve()
    path = entry.path.resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError(f"Refusing to delete an unsafe path: {path}")
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def format_size(size_bytes: int) -> str:
    value = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")
