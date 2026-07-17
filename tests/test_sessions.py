from datetime import datetime, timedelta
from io import BytesIO

import numpy as np
from PIL import Image
import pytest

from muselens.sessions import (
    StagedSessionFile,
    TemporaryGalleryCapacityError,
    TemporaryGalleryService,
)


class FakeEncoder:
    model_id = "fake-session-encoder"
    loaded = True

    def __init__(self) -> None:
        self.image_batch_sizes: list[int] = []

    def encode_images(self, images: list[Image.Image]) -> np.ndarray:
        self.image_batch_sizes.append(len(images))
        vectors = []
        for image in images:
            red, _green, blue = np.asarray(image, dtype=np.float32).mean(axis=(0, 1))
            vectors.append([red + 1.0, blue + 1.0])
        return np.asarray(vectors, dtype=np.float32)

    def encode_texts(self, texts: list[str]) -> np.ndarray:
        return np.asarray(
            [[1.0, 0.0] if "red" in text else [0.0, 1.0] for text in texts],
            dtype=np.float32,
        )


def staged_image(service, session_id: str, filename: str, color: str) -> StagedSessionFile:
    staging = service.staging_dir(session_id)
    staging.mkdir(parents=True, exist_ok=True)
    path = staging / filename
    content = BytesIO()
    Image.new("RGB", (12, 12), color).save(content, format="PNG")
    path.write_bytes(content.getvalue())
    return StagedSessionFile(filename, "image/png", path)


def test_temporary_galleries_are_isolated_and_expire(tmp_path) -> None:
    service = TemporaryGalleryService(
        tmp_path / "sessions",
        FakeEncoder(),
        ttl_seconds=60,
    )
    service.initialize()

    service.create("red-session", [staged_image(service, "red-session", "red.png", "red")])
    service.create("blue-session", [staged_image(service, "blue-session", "blue.png", "blue")])
    service.run("red-session")
    service.run("blue-session")

    red = service.gallery("red-session")
    blue = service.gallery("blue-session")
    assert [image.filename for image in red.index.list_images()] == ["red.png"]
    assert [image.filename for image in blue.index.list_images()] == ["blue.png"]
    assert service.get("red-session").status == "completed"
    assert service.get("blue-session").status == "completed"

    red_hit = red.index.search(service.encoder.encode_texts(["red photo"])[0], top_k=1)[0]
    assert red_hit.image.filename == "red.png"

    red.expires_at = datetime.now(red.expires_at.tzinfo) - timedelta(seconds=1)
    assert service.cleanup_expired() == 1
    assert not (service.root / "red-session").exists()
    with pytest.raises(KeyError):
        service.get("red-session")
    assert service.get("blue-session").status == "completed"


def test_temporary_gallery_capacity_is_bounded(tmp_path) -> None:
    service = TemporaryGalleryService(
        tmp_path / "sessions",
        FakeEncoder(),
        max_sessions=1,
    )
    service.initialize()
    service.create("first", [staged_image(service, "first", "one.png", "red")])

    with pytest.raises(TemporaryGalleryCapacityError):
        service.create("second", [staged_image(service, "second", "two.png", "blue")])


def test_running_gallery_cannot_be_deleted(tmp_path) -> None:
    service = TemporaryGalleryService(tmp_path / "sessions", FakeEncoder())
    service.initialize()
    service.create("active", [staged_image(service, "active", "one.png", "red")])

    with pytest.raises(RuntimeError, match="still being indexed"):
        service.delete("active")

    service.run("active")
    assert service.delete("active") is True
    assert service.delete("active") is False


def test_temporary_gallery_encodes_valid_images_in_one_batch(tmp_path) -> None:
    encoder = FakeEncoder()
    service = TemporaryGalleryService(tmp_path / "sessions", encoder)
    service.initialize()
    session_id = "batch"
    staged = [
        staged_image(service, session_id, "one.png", "red"),
        staged_image(service, session_id, "two.png", "blue"),
        staged_image(service, session_id, "three.png", "green"),
    ]

    service.create(session_id, staged)
    service.run(session_id)

    assert encoder.image_batch_sizes == [3]
    assert service.get(session_id).imported_files == 3
