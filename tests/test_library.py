from io import BytesIO

import numpy as np
from PIL import Image, ImageDraw
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


def patterned_bytes(*, size: tuple[int, int] = (180, 120), quality: int = 90) -> bytes:
    image = Image.new("RGB", (180, 120), (220, 190, 120))
    draw = ImageDraw.Draw(image)
    draw.rectangle((12, 15, 84, 105), fill=(32, 75, 135))
    draw.ellipse((92, 20, 164, 92), fill=(210, 55, 60))
    draw.line((0, 119, 179, 0), fill=(245, 245, 230), width=7)
    image = image.resize(size, Image.Resampling.LANCZOS)
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
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


def test_library_groups_transformed_duplicates_and_deletes_only_its_copy(tmp_path) -> None:
    repository = ImageRepository(tmp_path / "state" / "index.sqlite3")
    repository.initialize()
    index = VectorIndex()
    library = ImageLibrary(tmp_path / "images", repository, index, FakeEncoder())
    candidates = [
        prepare_image("original.jpg", "image/jpeg", patterned_bytes(), 1024 * 1024),
        prepare_image(
            "compressed.jpg",
            "image/jpeg",
            patterned_bytes(size=(96, 64), quality=42),
            1024 * 1024,
        ),
        prepare_image("different.jpg", "image/jpeg", jpeg_bytes("blue"), 1024 * 1024),
    ]
    library.import_candidates(candidates)

    groups = library.duplicate_groups()

    assert len(groups) == 1
    assert {member.stored.image.filename for member in groups[0].members} == {
        "original.jpg",
        "compressed.jpg",
    }
    assert sum(member.recommended_keep for member in groups[0].members) == 1
    removable = next(member for member in groups[0].members if not member.recommended_keep)
    original_path = library.original_path(removable.stored)
    thumbnail_path = library.thumbnail_path(removable.stored.image.image_id)
    assert original_path.is_file()
    assert thumbnail_path.is_file()

    deleted = library.delete_imported_copy(removable.stored.image.image_id)

    assert deleted == removable.stored
    assert repository.find_by_id(removable.stored.image.image_id) is None
    assert not original_path.exists()
    assert not thumbnail_path.exists()
    assert len(index) == 2


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
