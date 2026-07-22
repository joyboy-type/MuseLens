"""Report and safely remove MuseLens-generated local experiment data."""

import argparse
from pathlib import Path

from muselens.cleanup import cleanup_entries, format_size, remove_entry


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preview or remove reproducible MuseLens experiment data."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete listed paths. Without this flag the command is read-only.",
    )
    parser.add_argument(
        "--include-feature-cache",
        action="store_true",
        help="Also remove frozen model feature caches; reports and trained weights are preserved.",
    )
    args = parser.parse_args()

    entries = cleanup_entries(
        PROJECT_ROOT,
        include_feature_cache=args.include_feature_cache,
    )
    total = sum(entry.size_bytes for entry in entries)
    action = "DELETE" if args.apply else "PREVIEW"
    print(f"mode={action.lower()}")
    for entry in entries:
        relative = entry.path.relative_to(PROJECT_ROOT)
        print(f"{action} {relative} ({format_size(entry.size_bytes)})")
    print(f"reclaimable={format_size(total)}")

    if args.apply:
        for entry in entries:
            remove_entry(entry, PROJECT_ROOT)
        print(f"deleted_paths={len(entries)}")
    else:
        print("No files were deleted. Re-run with --apply to confirm cleanup.")


if __name__ == "__main__":
    main()
