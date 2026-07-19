import os
import json
from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_modelscope_deployment_is_a_guarded_docker_demo() -> None:
    deployment = json.loads((PROJECT_ROOT / "ms_deploy.json").read_text())
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text()
    variables = {
        item["name"]: item["value"]
        for item in deployment["environment_variables"]
    }

    assert deployment["sdk_type"] == "docker"
    assert deployment["port"] == 7860
    assert variables["MUSELENS_MODE"] == "demo"
    assert variables["MUSELENS_SEARCH_MIN_SCORE"] == "-1"
    # ModelScope may ignore ms_deploy environment variables and cannot reach
    # huggingface.co at runtime, so the image itself must be safe and offline.
    assert "MUSELENS_MODE=demo" in dockerfile
    assert "HF_HUB_OFFLINE=1" in dockerfile
    assert "TRANSFORMERS_OFFLINE=1" in dockerfile


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


def test_modelscope_package_contains_only_runtime_release_files(tmp_path) -> None:
    output = tmp_path / "release"
    subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "package_modelscope.py"), str(output)],
        cwd=PROJECT_ROOT,
        check=True,
    )

    assert (output / "Dockerfile").is_file()
    assert (output / "ms_deploy.json").is_file()
    assert (output / "README.md").read_text().startswith("# MuseLens 多模态图片检索")
    assert (output / "demo_assets" / "manifest.json").is_file()
    assert not (output / "tests").exists()
    assert not (output / "data").exists()
    assert not (output / "artifacts").exists()


def test_modelscope_publisher_validates_without_authentication(tmp_path) -> None:
    output = tmp_path / "release"
    subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "package_modelscope.py"), str(output)],
        cwd=PROJECT_ROOT,
        check=True,
    )
    environment = os.environ.copy()
    environment.pop("MODELSCOPE_API_TOKEN", None)

    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "publish_modelscope.py"),
            str(output),
            "--repo-id",
            "owner/MuseLens",
            "--dry-run",
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "modelscope_release_valid=true" in result.stdout


def test_modelscope_publisher_pushes_to_a_git_remote(tmp_path) -> None:
    output = tmp_path / "release"
    remote = tmp_path / "studio.git"
    seed = tmp_path / "seed"
    subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "package_modelscope.py"), str(output)],
        cwd=PROJECT_ROOT,
        check=True,
    )
    subprocess.run(["git", "init", "--bare", "--initial-branch=master", str(remote)], check=True)
    subprocess.run(["git", "init", "--initial-branch=master", str(seed)], check=True)
    (seed / "README.md").write_text("seed\n")
    subprocess.run(["git", "-C", str(seed), "add", "README.md"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(seed),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-m",
            "Seed",
        ],
        check=True,
    )
    subprocess.run(["git", "-C", str(seed), "remote", "add", "origin", str(remote)], check=True)
    subprocess.run(["git", "-C", str(seed), "push", "origin", "master"], check=True)

    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "publish_modelscope.py"),
            str(output),
            "--repo-url",
            str(remote),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "modelscope_push_changed=true" in result.stdout
    tree = subprocess.run(
        ["git", "--git-dir", str(remote), "ls-tree", "--name-only", "master"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    assert "Dockerfile" in tree
    assert "ms_deploy.json" in tree
    assert "tests" not in tree

    second_result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "publish_modelscope.py"),
            str(output),
            "--repo-url",
            str(remote),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert second_result.returncode == 0, second_result.stderr
    assert "modelscope_push_changed=false" in second_result.stdout
