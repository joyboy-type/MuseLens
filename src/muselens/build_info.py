from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from . import __version__


DEFAULT_BUILD_COMMIT = "local"
RELEASE_METADATA_PATH = Path.cwd() / ".muselens-release.json"


def load_build_info() -> dict[str, str]:
    """Return immutable release identity without requiring platform build arguments."""
    commit = os.environ.get("MUSELENS_BUILD_COMMIT", "").strip()
    version = __version__
    metadata_path = Path(
        os.environ.get("MUSELENS_RELEASE_METADATA", RELEASE_METADATA_PATH)
    )
    if metadata_path.is_file():
        try:
            payload: Any = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        if isinstance(payload, dict):
            file_commit = payload.get("commit")
            file_version = payload.get("version")
            if not commit and isinstance(file_commit, str) and file_commit.strip():
                commit = file_commit.strip()
            if isinstance(file_version, str) and file_version.strip():
                version = file_version.strip()
    return {
        "version": version,
        "commit": commit or DEFAULT_BUILD_COMMIT,
    }


BUILD_INFO = load_build_info()
