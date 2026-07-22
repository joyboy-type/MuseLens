from io import BytesIO

from fastapi.testclient import TestClient
import numpy as np
from PIL import Image, ImageDraw

from muselens.api import app, seed_demo_library
from muselens.index import IndexedImage, VectorIndex
from muselens.library import ImageLibrary, prepare_image
from muselens.repository import ImageRepository
from muselens.sessions import TemporaryGalleryService
from muselens.tags import DEFAULT_TAGS, ImageTag


class TemporaryEncoder:
    model_id = "temporary-api-encoder"
    loaded = True

    def encode_images(self, images: list[Image.Image]) -> np.ndarray:
        return np.asarray([[1.0, 0.0] for _image in images], dtype=np.float32)

    def encode_texts(self, texts: list[str]) -> np.ndarray:
        # Deliberately tiny cosine score: a temporary gallery must still return
        # its best ranked match instead of applying a large-corpus absolute floor.
        return np.asarray([[0.01, np.sqrt(0.9999)] for _text in texts], dtype=np.float32)


class CorrectableTagger:
    model_id = "temporary-api-encoder:tags-v1"
    definitions = DEFAULT_TAGS

    def predict(self, vector: np.ndarray) -> tuple[ImageTag, ...]:
        return (ImageTag("dog", "狗", 0.8, "auto"),)


def patterned_jpeg(*, size: tuple[int, int] = (180, 120), quality: int = 90) -> bytes:
    image = Image.new("RGB", (180, 120), (220, 190, 120))
    draw = ImageDraw.Draw(image)
    draw.rectangle((12, 15, 84, 105), fill=(32, 75, 135))
    draw.ellipse((92, 20, 164, 92), fill=(210, 55, 60))
    draw.line((0, 119, 179, 0), fill=(245, 245, 230), width=7)
    image = image.resize(size, Image.Resampling.LANCZOS)
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


def test_health_reports_service_status() -> None:
    with TestClient(app) as client:
        app.state.index = VectorIndex()
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["indexed_images"] == 0
    assert isinstance(response.json()["model_loaded"], bool)
    assert response.json()["reranker_enabled"] is False
    assert response.json()["reranker_loaded"] is False
    assert response.json()["index_backend"] == "mmap"
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


def test_duplicate_api_groups_transforms_and_deletes_only_imported_copy(tmp_path) -> None:
    repository = ImageRepository(tmp_path / "state" / "index.sqlite3")
    repository.initialize()
    index = VectorIndex()
    library = ImageLibrary(tmp_path / "library", repository, index, TemporaryEncoder())
    original = patterned_jpeg()
    compressed = patterned_jpeg(size=(96, 64), quality=42)
    source_file = tmp_path / "source-original.jpg"
    source_file.write_bytes(original)
    imported = library.import_candidates(
        [
            prepare_image("original.jpg", "image/jpeg", original, 1024 * 1024),
            prepare_image("compressed.jpg", "image/jpeg", compressed, 1024 * 1024),
        ]
    )

    with TestClient(app) as client:
        app.state.library = library
        app.state.index = index
        app.state.library_writable = True
        response = client.get("/v1/duplicates")
        assert response.status_code == 200
        groups = response.json()
        assert len(groups) == 1
        assert len(groups[0]["members"]) == 2
        assert sum(member["recommended_keep"] for member in groups[0]["members"]) == 1
        remove_id = next(
            member["image_id"] for member in groups[0]["members"] if not member["recommended_keep"]
        )

        deleted = client.delete(f"/v1/images/{remove_id}")

    assert deleted.status_code == 204
    assert source_file.is_file()
    assert repository.find_by_id(remove_id) is None
    assert len(index) == 1
    assert len(imported) == 2


def test_demo_mode_rejects_deleting_an_image() -> None:
    with TestClient(app) as client:
        app.state.library_writable = False
        response = client.delete("/v1/images/unknown")

    assert response.status_code == 403


def test_tag_catalog_and_local_manual_tag_correction(tmp_path) -> None:
    repository = ImageRepository(tmp_path / "state" / "index.sqlite3")
    repository.initialize()
    index = VectorIndex()
    library = ImageLibrary(
        tmp_path / "library",
        repository,
        index,
        TemporaryEncoder(),
        tagger=CorrectableTagger(),
    )
    stored = library.import_candidates(
        [
            prepare_image(
                "pet.jpg",
                "image/jpeg",
                patterned_jpeg(),
                1024 * 1024,
            )
        ]
    )[0].stored

    with TestClient(app) as client:
        app.state.library = library
        app.state.index = index
        app.state.library_writable = True

        catalog = client.get("/v1/tags/catalog")
        corrected = client.put(
            f"/v1/images/{stored.image.image_id}/tags",
            json={"tags": ["cat", "indoor", "cat"]},
        )
        restored = client.post(f"/v1/images/{stored.image.image_id}/tags/auto")

    assert catalog.status_code == 200
    assert {item["slug"] for item in catalog.json()} >= {"dog", "cat", "indoor"}
    assert [(tag["slug"], tag["source"]) for tag in corrected.json()["tags"]] == [
        ("cat", "manual"),
        ("indoor", "manual"),
    ]
    assert [(tag["slug"], tag["source"]) for tag in restored.json()["tags"]] == [("dog", "auto")]


def test_demo_mode_rejects_manual_tag_correction() -> None:
    with TestClient(app) as client:
        app.state.library_writable = False
        response = client.put("/v1/images/unknown/tags", json={"tags": ["dog"]})

    assert response.status_code == 403


def test_custom_album_lifecycle_is_persisted_and_local_only(tmp_path) -> None:
    repository = ImageRepository(tmp_path / "state" / "index.sqlite3")
    repository.initialize()
    index = VectorIndex()
    library = ImageLibrary(tmp_path / "images", repository, index, TemporaryEncoder())
    stored = library.import_candidates(
        [prepare_image("memory.jpg", "image/jpeg", patterned_jpeg(), 1024 * 1024)]
    )[0].stored

    with TestClient(app) as client:
        app.state.library = library
        app.state.index = index
        app.state.library_writable = True
        created = client.post("/v1/albums", json={"name": "  暑假   旅行  "})
        album_id = created.json()["album_id"]
        added = client.put(
            f"/v1/albums/{album_id}/images",
            json={"image_id": stored.image.image_id, "present": True},
        )
        renamed = client.put(f"/v1/albums/{album_id}", json={"name": "毕业旅行"})
        listed = client.get("/v1/albums")
        deleted = client.delete(f"/v1/albums/{album_id}")

    assert created.status_code == 201
    assert created.json()["name"] == "暑假 旅行"
    assert added.json()["image_ids"] == [stored.image.image_id]
    assert renamed.json()["name"] == "毕业旅行"
    assert listed.json() == [renamed.json() | {"image_ids": [stored.image.image_id]}]
    assert deleted.status_code == 204
    assert repository.list_albums() == []


def test_demo_mode_hides_and_rejects_custom_albums() -> None:
    with TestClient(app) as client:
        app.state.library_writable = False
        listed = client.get("/v1/albums")
        created = client.post("/v1/albums", json={"name": "不可写"})

    assert listed.json() == []
    assert created.status_code == 403


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
        content = client.get(f"/v1/demo/sessions/{session_id}/images/{image_id}/content")
        assert content.status_code == 200
        assert content.headers["cache-control"] == "private, no-store"

        search = client.post(
            f"/v1/demo/sessions/{session_id}/search/text",
            json={"query": "anything", "top_k": 5},
        )
        assert [item["filename"] for item in search.json()] == ["private.png"]

        image_search = client.post(
            f"/v1/demo/sessions/{session_id}/search/image",
            files={"file": ("query.png", image.getvalue(), "image/png")},
        )
        assert image_search.status_code == 200
        assert image_search.json() == []  # The exact query asset is not a useful similar result.

        assert client.get("/v1/demo/sessions/not-this-user/images").status_code == 404
        assert client.delete(f"/v1/demo/sessions/{session_id}").status_code == 204
