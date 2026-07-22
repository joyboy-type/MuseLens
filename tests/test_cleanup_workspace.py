from pathlib import Path

import pytest

from muselens.cleanup import cleanup_entries, format_size, remove_entry


def test_cleanup_is_previewable_and_scoped_to_regenerable_paths(tmp_path: Path) -> None:
    download = tmp_path / "data" / ".download-cache"
    download.mkdir(parents=True)
    (download / "archive.zip").write_bytes(b"1234")
    protected = tmp_path / "artifacts" / "evaluations" / "report.json"
    protected.parent.mkdir(parents=True)
    protected.write_text("{}")

    entries = cleanup_entries(tmp_path)

    assert [(entry.path, entry.size_bytes) for entry in entries] == [(download, 4)]
    assert protected.is_file()


def test_feature_cache_requires_explicit_opt_in(tmp_path: Path) -> None:
    cache = tmp_path / "artifacts" / "feature-cache"
    cache.mkdir(parents=True)
    (cache / "features.npz").write_bytes(b"123456")

    assert cleanup_entries(tmp_path) == []
    entries = cleanup_entries(tmp_path, include_feature_cache=True)
    assert len(entries) == 1

    remove_entry(entries[0], tmp_path)

    assert not cache.exists()


def test_human_readable_sizes() -> None:
    assert format_size(0) == "0.0 B"
    assert format_size(1536) == "1.5 KB"


def test_cleanup_refuses_a_generated_path_symlinked_outside_project(tmp_path: Path) -> None:
    project = tmp_path / "project"
    cache_parent = project / "data"
    cache_parent.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (cache_parent / ".download-cache").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="outside the project"):
        cleanup_entries(project)
