import os
from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_publish_space_cli_executes_main_and_requires_authentication(tmp_path) -> None:
    environment = os.environ.copy()
    environment["HF_HOME"] = str(tmp_path / "empty-hugging-face-home")
    environment.pop("HF_TOKEN", None)

    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "publish_space.py"),
            str(tmp_path / "source"),
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "HF_TOKEN or a local Hugging Face login is required" in result.stderr
