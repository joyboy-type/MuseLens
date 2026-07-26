from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import tomllib


PROJECT_ROOT = Path(__file__).resolve().parents[1]
COPY_ENTRIES = (
    "Dockerfile",
    ".dockerignore",
    "LICENSE",
    "pyproject.toml",
    "requirements-runtime.txt",
    "src",
    "frontend",
    "demo_assets",
    "ms_deploy.json",
)


def ignored(_directory: str, names: list[str]) -> set[str]:
    ignored_names = {"node_modules", "dist", ".next", ".openai", "__pycache__", ".DS_Store"}
    return {name for name in names if name in ignored_names or name.endswith(".tsbuildinfo")}


def package_modelscope(output: Path, commit: str = "local") -> None:
    output = output.resolve()
    if output == PROJECT_ROOT or output == PROJECT_ROOT / "src":
        raise ValueError("Refusing to overwrite a source directory.")
    shutil.rmtree(output, ignore_errors=True)
    output.mkdir(parents=True)

    for name in COPY_ENTRIES:
        source = PROJECT_ROOT / name
        destination = output / name
        if source.is_dir():
            shutil.copytree(source, destination, ignore=ignored)
        else:
            shutil.copy2(source, destination)

    shutil.copy2(PROJECT_ROOT / "deploy" / "modelscope" / "README.md", output / "README.md")
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as file:
        version = tomllib.load(file)["project"]["version"]
    (output / ".muselens-release.json").write_text(
        json.dumps({"commit": commit, "version": version}, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a clean ModelScope Studio source tree.")
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--commit",
        default="local",
        help="Source Git commit embedded in the release health identity.",
    )
    args = parser.parse_args()
    package_modelscope(args.output, args.commit)


if __name__ == "__main__":
    main()
