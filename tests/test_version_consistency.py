import json
from pathlib import Path
import tomllib

from muselens import __version__
from muselens.api import app


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_release_version_is_consistent_across_packages_and_api() -> None:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as file:
        python_version = tomllib.load(file)["project"]["version"]
    frontend_version = json.loads(
        (PROJECT_ROOT / "frontend" / "package.json").read_text(encoding="utf-8")
    )["version"]

    assert __version__ == python_version == frontend_version
    assert app.version == __version__
