from io import BytesIO

import numpy as np
from PIL import Image
import pytest

from muselens.index import VectorIndex
from muselens.library import ImageLibrary, prepare_image
from muselens.library import InvalidImageError
from muselens.repository import ImageRepository


class FakeEncoder:
    model_id = "fake-encoder"

    def encode_images(self, images):
        return np.tile(np.array([[1.0, 0.0]], dtype=np.float32), (len(images), 1))


class NewFakeEncoder:
    model_id = "new-fake-encoder"

    def encode_images(self, images):
        return np.tile(np.array([[0.0, 1.0, 0.0]], dtype=np.float32), (len(images), 1))


def jpeg_bytes(color: str) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (16, 16), color).save(buffer, format="JPEG")
    return buffer.getvalue()


def test_library_deduplicates_and_restores_index(tmp_path) -> None:
    repository = ImageRepository(tmp_path / "state" / "index.sqlite3")
    repository.initialize()
    index = VectorIndex()
    library = ImageLibrary(tmp_path / "images", repository, index, FakeEncoder())
    content = jpeg_bytes("red")
    candidates = [
        prepare_image("one.jpg", "image/jpeg", content, 1024 * 1024),
        prepare_image("copy.jpg", "image/jpeg", content, 1024 * 1024),
    ]

    results = library.import_candidates(candidates)

    assert [result.duplicate for result in results] == [False, True]
    assert results[0].stored.image.image_id == results[1].stored.image.image_id
    assert len(list((tmp_path / "images").glob("*.jpg"))) == 1
    thumbnail = library.thumbnail_path(results[0].stored.image.image_id)
    assert thumbnail.is_file()
    with Image.open(thumbnail) as rendered:
        assert rendered.format == "WEBP"
        assert max(rendered.size) <= 640

    restored_index = VectorIndex()
    restored_library = ImageLibrary(
        tmp_path / "images", repository, restored_index, FakeEncoder()
    )
    assert restored_library.restore_index() == 1
    assert len(restored_index) == 1


def test_library_lazily_rebuilds_a_missing_thumbnail(tmp_path) -> None:
    repository = ImageRepository(tmp_path / "state" / "index.sqlite3")
    repository.initialize()
    library = ImageLibrary(tmp_path / "images", repository, VectorIndex(), FakeEncoder())
    candidate = prepare_image(
        "wide.jpg",
        "image/jpeg",
        jpeg_bytes("blue"),
        1024 * 1024,
    )
    stored = library.import_candidates([candidate])[0].stored
    thumbnail = library.thumbnail_path(stored.image.image_id)
    thumbnail.unlink()

    rebuilt = library.ensure_thumbnail(stored)

    assert rebuilt == thumbnail
    assert rebuilt.is_file()


def test_library_rebuilds_embeddings_when_model_changes(tmp_path) -> None:
    repository = ImageRepository(tmp_path / "state" / "index.sqlite3")
    repository.initialize()
    image_dir = tmp_path / "images"
    original = ImageLibrary(image_dir, repository, VectorIndex(), FakeEncoder())
    original.import_candidates(
        [prepare_image("one.jpg", "image/jpeg", jpeg_bytes("red"), 1024 * 1024)]
    )

    new_index = VectorIndex()
    migrated = ImageLibrary(image_dir, repository, new_index, NewFakeEncoder())
    assert migrated.restore_index() == 0
    assert migrated.rebuild_embeddings() == 1
    assert migrated.restore_index() == 1
    assert len(new_index) == 1


def test_prepare_image_rejects_excessive_decoded_pixels() -> None:
    with pytest.raises(InvalidImageError, match="too many pixels"):
        prepare_image(
            "large.jpg",
            "image/jpeg",
            jpeg_bytes("red"),
            max_upload_bytes=1024 * 1024,
            max_image_pixels=100,
        )
