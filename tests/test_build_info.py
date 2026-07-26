import json

from muselens.build_info import load_build_info


def test_build_info_reads_explicit_container_metadata(monkeypatch, tmp_path) -> None:
    metadata = tmp_path / ".muselens-release.json"
    metadata.write_text(
        json.dumps({"version": "0.1.2", "commit": "4f823586"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("MUSELENS_RELEASE_METADATA", str(metadata))
    monkeypatch.delenv("MUSELENS_BUILD_COMMIT", raising=False)

    assert load_build_info() == {
        "version": "0.1.2",
        "commit": "4f823586",
    }
