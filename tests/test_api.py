from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from muselens.api import app, seed_demo_library
from muselens.index import VectorIndex


def test_health_reports_service_status() -> None:
    with TestClient(app) as client:
        app.state.index = VectorIndex()
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["indexed_images"] == 0
    assert isinstance(response.json()["model_loaded"], bool)
    assert response.json()["mode"] == "local"
    assert response.json()["library_writable"] is True


def test_empty_library_can_be_searched_without_loading_clip() -> None:
    with TestClient(app) as client:
        app.state.index = VectorIndex()
        response = client.post("/v1/search/text", json={"query": "sunset", "top_k": 5})
    assert response.status_code == 200
    assert response.json() == []


def test_demo_mode_rejects_library_mutation() -> None:
    image = BytesIO()
    Image.new("RGB", (8, 8), "green").save(image, format="PNG")

    with TestClient(app) as client:
        app.state.mode = "demo"
        app.state.library_writable = False
        response = client.post(
            "/v1/images",
            files={"file": ("query.png", image.getvalue(), "image/png")},
        )

    assert response.status_code == 403
    assert "fixed image library" in response.json()["detail"]


def test_demo_seed_populates_precreated_runtime_directories(tmp_path) -> None:
    seed = tmp_path / "seed"
    (seed / "images").mkdir(parents=True)
    (seed / "state").mkdir()
    (seed / "thumbnails").mkdir()
    (seed / "images" / "sample.jpg").write_bytes(b"image")
    (seed / "state" / "index.sqlite3").write_bytes(b"database")
    (seed / "thumbnails" / "sample.webp").write_bytes(b"thumbnail")

    runtime = tmp_path / "runtime"
    images = runtime / "images"
    state = runtime / "state"
    thumbnails = runtime / "thumbnails"
    images.mkdir(parents=True)
    state.mkdir()
    thumbnails.mkdir()

    seed_demo_library(seed, images, state, thumbnails)

    assert (images / "sample.jpg").read_bytes() == b"image"
    assert (state / "index.sqlite3").read_bytes() == b"database"
    assert (thumbnails / "sample.webp").read_bytes() == b"thumbnail"
