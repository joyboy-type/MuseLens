import os
import json
from io import BytesIO
from pathlib import Path
import subprocess
import sys
from urllib.error import HTTPError

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts import publish_modelscope, wait_for_deployment  # noqa: E402


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
    assert "MUSELENS_RELEASE_METADATA=/app/.muselens-release.json" in dockerfile
    # Create and hand off the persistent model directory before downloading
    # weights. Chowning it afterwards duplicates the 1.4 GB model in a new layer.
    model_download = dockerfile.index("AutoProcessor.from_pretrained")
    assert dockerfile.index("chown -R muselens:muselens /data") < model_download
    assert dockerfile.index("USER muselens") < model_download
    # Application-only changes must not invalidate the large model cache layer.
    assert dockerfile.index("COPY requirements-runtime.txt") < model_download
    assert model_download < dockerfile.index("COPY pyproject.toml")
    assert model_download < dockerfile.index("COPY src/")


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
    assert (output / "requirements-runtime.txt").is_file()
    assert json.loads((output / ".muselens-release.json").read_text()) == {
        "commit": "local",
        "version": "0.1.2",
    }
    readme = (output / "README.md").read_text()
    assert readme.startswith("---\ntags:")
    assert "# MuseLens 多模态图片检索" in readme
    assert "multimodal" in readme
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

    environment = os.environ.copy()
    environment["MODELSCOPE_API_TOKEN"] = "test-token-never-transmitted"
    unchanged_deploy = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "publish_modelscope.py"),
            str(output),
            "--repo-id",
            "owner/MuseLens",
            "--repo-url",
            str(remote),
            "--deploy-if-changed",
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert unchanged_deploy.returncode == 0, unchanged_deploy.stderr
    assert "modelscope_push_changed=false" in unchanged_deploy.stdout
    assert "modelscope_deploy_triggered=false" in unchanged_deploy.stdout


def test_modelscope_package_embeds_source_commit(tmp_path) -> None:
    output = tmp_path / "release"
    commit = "a" * 40
    subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "package_modelscope.py"),
            str(output),
            "--commit",
            commit,
        ],
        cwd=PROJECT_ROOT,
        check=True,
    )

    metadata = json.loads((output / ".muselens-release.json").read_text())
    assert metadata == {"commit": commit, "version": "0.1.2"}


def test_deployment_trigger_retries_transient_http_error(monkeypatch) -> None:
    calls = 0

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b'{"Success": true}'

    def fake_urlopen(_request, timeout):
        nonlocal calls
        calls += 1
        assert timeout == 60
        if calls == 1:
            raise HTTPError(
                "https://modelscope.cn",
                503,
                "unavailable",
                {},
                BytesIO(b"temporary"),
            )
        return Response()

    monkeypatch.setattr(publish_modelscope, "urlopen", fake_urlopen)
    monkeypatch.setattr(publish_modelscope, "sleep", lambda _seconds: None)

    result = publish_modelscope.trigger_deployment(
        "owner/MuseLens",
        "token",
        retry_delay=0,
    )

    assert calls == 2
    assert result == {"Success": True}


def test_explicit_deploy_runs_even_when_git_tree_is_unchanged(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    source = tmp_path / "release"
    source.mkdir()
    for name in publish_modelscope.REQUIRED_FILES:
        (source / name).write_text("{}" if name == "ms_deploy.json" else "test")
    (source / "ms_deploy.json").write_text(
        json.dumps(
            {
                "sdk_type": "docker",
                "port": 7860,
                "environment_variables": [{"name": "MUSELENS_MODE", "value": "demo"}],
            }
        )
    )
    args = type(
        "Args",
        (),
        {
            "source": source,
            "repo_id": "owner/MuseLens",
            "repo_url": "file:///unused",
            "branch": "master",
            "deploy": True,
            "deploy_if_changed": False,
            "dry_run": False,
        },
    )()
    triggered = []
    monkeypatch.setattr(publish_modelscope, "parse_args", lambda: args)
    monkeypatch.setattr(publish_modelscope, "publish_git", lambda *_args: False)
    monkeypatch.setattr(
        publish_modelscope,
        "trigger_deployment",
        lambda repo_id, token: triggered.append((repo_id, token)),
    )
    monkeypatch.setenv("MODELSCOPE_API_TOKEN", "token")

    publish_modelscope.main()

    assert triggered == [("owner/MuseLens", "token")]
    assert "modelscope_push_changed=false" in capsys.readouterr().out


def test_wait_gate_rejects_same_version_from_wrong_commit(monkeypatch) -> None:
    health = {
        "status": "ok",
        "version": "0.1.2",
        "commit": "old-commit",
        "mode": "demo",
        "library_writable": False,
        "temporary_galleries_enabled": True,
        "indexed_images": 10,
    }

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return json.dumps(health).encode()

    monkeypatch.setattr(wait_for_deployment, "urlopen", lambda *_args, **_kwargs: Response())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "wait_for_deployment.py",
            "https://example.test",
            "--expected-commit",
            "new-commit",
            "--timeout",
            "0.01",
            "--interval",
            "0.01",
        ],
    )

    with pytest.raises(SystemExit, match="Expected commit 'new-commit'"):
        wait_for_deployment.main()


def test_wait_gate_fails_immediately_on_terminal_modelscope_state(
    monkeypatch,
) -> None:
    monkeypatch.setenv("MODELSCOPE_API_TOKEN", "token")
    monkeypatch.setattr(
        wait_for_deployment,
        "fetch_json",
        lambda *_args, **_kwargs: {"Data": {"Status": "Failed"}},
    )
    monkeypatch.setattr(wait_for_deployment, "fetch_failure_logs", lambda *_args: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "wait_for_deployment.py",
            "https://example.test",
            "--studio-id",
            "owner/MuseLens",
        ],
    )

    with pytest.raises(SystemExit, match="terminal state 'Failed'"):
        wait_for_deployment.main()


@pytest.mark.parametrize("status", ["Failed", "BuildFailed", "RuntimeError", "Stopped"])
def test_modelscope_composite_failure_states_are_terminal(status) -> None:
    assert wait_for_deployment.is_failed_status(status)
