from io import BytesIO

from fastapi.testclient import TestClient
import numpy as np
from PIL import Image

from muselens.api import app, seed_demo_library
from muselens.index import IndexedImage, VectorIndex
from muselens.sessions import TemporaryGalleryService


class TemporaryEncoder:
    model_id = "temporary-api-encoder"
    loaded = True

    def encode_images(self, images: list[Image.Image]) -> np.ndarray:
        return np.asarray([[1.0, 0.0] for _image in images], dtype=np.float32)

    def encode_texts(self, texts: list[str]) -> np.ndarray:
        # Deliberately tiny cosine score: a temporary gallery must still return
        # its best ranked match instead of applying a large-corpus absolute floor.
        return np.asarray([[0.01, np.sqrt(0.9999)] for _text in texts], dtype=np.float32)


def test_health_reports_service_status() -> None:
    with TestClient(app) as client:
        app.state.index = VectorIndex()
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["indexed_images"] == 0
    assert isinstance(response.json()["model_loaded"], bool)
    assert response.json()["index_backend"] == "numpy"
    assert response.json()["mode"] == "local"
    assert response.json()["library_writable"] is True
    assert response.json()["temporary_galleries_enabled"] is False


def test_empty_library_can_be_searched_without_loading_clip() -> None:
    with TestClient(app) as client:
        app.state.index = VectorIndex()
        response = client.post("/v1/search/text", json={"query": "sunset", "top_k": 5})
    assert response.status_code == 200
    assert response.json() == []


def test_local_library_keeps_best_ranked_match_below_demo_floor() -> None:
    index = VectorIndex()
    index.add(
        image=IndexedImage("one", "one.jpg", "image/jpeg"),
        vector=np.asarray([1.0, 0.0], dtype=np.float32),
    )
    with TestClient(app) as client:
        app.state.mode = "local"
        app.state.index = index
        app.state.encoder = TemporaryEncoder()
        response = client.post("/v1/search/text", json={"query": "short label", "top_k": 5})

    assert response.status_code == 200
    assert [item["filename"] for item in response.json()] == ["one.jpg"]


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


def test_temporary_gallery_api_indexes_and_isolates_uploads(tmp_path) -> None:
    image = BytesIO()
    Image.new("RGB", (10, 10), "purple").save(image, format="PNG")

    with TestClient(app) as client:
        service = TemporaryGalleryService(tmp_path / "sessions", TemporaryEncoder())
        service.initialize()
        app.state.temporary_galleries_enabled = True
        app.state.temporary_gallery_service = service

        created = client.post(
            "/v1/demo/sessions",
            files=[("files", ("private.png", image.getvalue(), "image/png"))],
        )
        assert created.status_code == 202
        session_id = created.json()["session_id"]

        status = client.get(f"/v1/demo/sessions/{session_id}")
        assert status.json()["status"] == "completed"
        assert status.json()["imported_files"] == 1

        images = client.get(f"/v1/demo/sessions/{session_id}/images")
        assert [item["filename"] for item in images.json()] == ["private.png"]
        image_id = images.json()[0]["image_id"]
        content = client.get(
            f"/v1/demo/sessions/{session_id}/images/{image_id}/content"
        )
        assert content.status_code == 200
        assert content.headers["cache-control"] == "private, no-store"

        search = client.post(
            f"/v1/demo/sessions/{session_id}/search/text",
            json={"query": "anything", "top_k": 5},
        )
        assert [item["filename"] for item in search.json()] == ["private.png"]

        assert client.get("/v1/demo/sessions/not-this-user/images").status_code == 404
        assert client.delete(f"/v1/demo/sessions/{session_id}").status_code == 204
