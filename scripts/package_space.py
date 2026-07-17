from __future__ import annotations

import argparse
from pathlib import Path
import shutil


PROJECT_ROOT = Path(__file__).resolve().parents[1]
COPY_ENTRIES = (
    "Dockerfile",
    ".dockerignore",
    "LICENSE",
    "pyproject.toml",
    "src",
    "frontend",
    "demo_assets",
)


def ignored(_directory: str, names: list[str]) -> set[str]:
    ignored_names = {"node_modules", "dist", ".next", ".openai", "__pycache__", ".DS_Store"}
    return {name for name in names if name in ignored_names or name.endswith(".tsbuildinfo")}


def package_space(output: Path) -> None:
    output = output.resolve()
    if output == PROJECT_ROOT or PROJECT_ROOT in output.parents and output.name == "src":
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

    shutil.copy2(PROJECT_ROOT / "deploy" / "huggingface" / "README.md", output / "README.md")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a clean Hugging Face Space source tree.")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    package_space(args.output)


if __name__ == "__main__":
    main()
