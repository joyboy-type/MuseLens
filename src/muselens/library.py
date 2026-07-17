from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from .encoder import ClipEncoder
from .index import IndexedImage, SearchIndex
from .repository import ImageRepository, StoredImage


SUPPORTED_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


class InvalidImageError(ValueError):
    pass


@dataclass(frozen=True)
class UploadCandidate:
    filename: str
    content_type: str
    content: bytes
    image: Image.Image
    digest: str


@dataclass(frozen=True)
class ImportResult:
    stored: StoredImage
    duplicate: bool


def prepare_image(
    filename: str,
    content_type: str,
    content: bytes,
    max_upload_bytes: int,
    max_image_pixels: int = 40_000_000,
) -> UploadCandidate:
    if content_type not in SUPPORTED_CONTENT_TYPES:
        raise InvalidImageError("Only JPEG, PNG and WebP images are supported.")
    if len(content) > max_upload_bytes:
        raise InvalidImageError("Uploaded image is too large.")
    try:
        with Image.open(BytesIO(content)) as opened:
            if opened.width * opened.height > max_image_pixels:
                raise InvalidImageError("The image contains too many pixels.")
            image = ImageOps.exif_transpose(opened).convert("RGB")
    except Image.DecompressionBombError as error:
        raise InvalidImageError("The image contains too many pixels.") from error
    except (UnidentifiedImageError, OSError) as error:
        raise InvalidImageError("The uploaded file is not a valid image.") from error
    return UploadCandidate(
        filename=filename,
        content_type=content_type,
        content=content,
        image=image,
        digest=sha256(content).hexdigest(),
    )


class ImageLibrary:
    def __init__(
        self,
        image_dir: Path,
        repository: ImageRepository,
        index: SearchIndex,
        encoder: ClipEncoder,
        thumbnail_dir: Path | None = None,
        thumbnail_max_size: int = 640,
        thumbnail_quality: int = 82,
    ) -> None:
        self.image_dir = image_dir
        self.repository = repository
        self.index = index
        self.encoder = encoder
        self.thumbnail_dir = thumbnail_dir or image_dir / ".muselens" / "thumbnails" / "v1"
        self.thumbnail_max_size = thumbnail_max_size
        self.thumbnail_quality = thumbnail_quality

    def restore_index(self) -> int:
        entries = self.repository.load_index(model_id=self.encoder.model_id)
        for stored, vector in entries:
            self.index.add(stored.image, vector)
        return len(entries)

    def rebuild_embeddings(self, batch_size: int = 16) -> int:
        """Re-encode stored originals, then atomically switch the persisted model."""
        entries = self.repository.load_index()
        if not entries:
            self.index.clear()
            return 0

        embeddings: list[tuple[str, np.ndarray]] = []
        for start in range(0, len(entries), batch_size):
            batch = entries[start : start + batch_size]
            images: list[Image.Image] = []
            try:
                for stored, _ in batch:
                    with Image.open(self.original_path(stored)) as opened:
                        images.append(ImageOps.exif_transpose(opened).convert("RGB"))
                vectors = self.encoder.encode_images(images)
            finally:
                for image in images:
                    image.close()
            embeddings.extend(
                (stored.image.image_id, vector)
                for (stored, _), vector in zip(batch, vectors, strict=True)
            )

        self.repository.replace_embeddings(embeddings, self.encoder.model_id)
        self.index.clear()
        for (stored, _), (_, vector) in zip(entries, embeddings, strict=True):
            self.index.add(stored.image, vector)
        return len(embeddings)

    def import_candidates(self, candidates: list[UploadCandidate]) -> list[ImportResult]:
        results: list[ImportResult | None] = [None] * len(candidates)
        unique_new: dict[str, tuple[UploadCandidate, list[int]]] = {}

        for position, candidate in enumerate(candidates):
            existing = self.repository.find_by_sha256(candidate.digest)
            if existing:
                results[position] = ImportResult(stored=existing, duplicate=True)
                continue
            if candidate.digest in unique_new:
                unique_new[candidate.digest][1].append(position)
            else:
                unique_new[candidate.digest] = (candidate, [position])

        pending = list(unique_new.values())
        if pending:
            vectors = self._encode_in_batches([item[0].image for item in pending])
            for (candidate, positions), vector in zip(pending, vectors, strict=True):
                stored = self._persist(candidate, vector)
                self.index.add(stored.image, vector)
                for offset, position in enumerate(positions):
                    results[position] = ImportResult(stored=stored, duplicate=offset > 0)

        return [result for result in results if result is not None]

    def _encode_in_batches(self, images: list[Image.Image], batch_size: int = 16) -> np.ndarray:
        batches = [
            self.encoder.encode_images(images[start : start + batch_size])
            for start in range(0, len(images), batch_size)
        ]
        return np.concatenate(batches)

    def _persist(self, candidate: UploadCandidate, vector: np.ndarray) -> StoredImage:
        self.image_dir.mkdir(parents=True, exist_ok=True)
        image_id = uuid4().hex
        suffix = SUPPORTED_CONTENT_TYPES[candidate.content_type]
        stored_filename = f"{image_id}{suffix}"
        destination = self.image_dir / stored_filename
        temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_bytes(candidate.content)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        stored = StoredImage(
            image=IndexedImage(
                image_id=image_id,
                filename=candidate.filename,
                content_type=candidate.content_type,
            ),
            stored_filename=stored_filename,
            sha256=candidate.digest,
            size_bytes=len(candidate.content),
            model_id=self.encoder.model_id,
        )
        try:
            self._write_thumbnail(candidate.image, self.thumbnail_path(image_id))
            self.repository.insert(stored, vector)
        except Exception:
            destination.unlink(missing_ok=True)
            self.thumbnail_path(image_id).unlink(missing_ok=True)
            raise
        return stored

    def original_path(self, stored: StoredImage) -> Path:
        return self.image_dir / stored.stored_filename

    def thumbnail_path(self, image_id: str) -> Path:
        return self.thumbnail_dir / f"{image_id}.webp"

    def ensure_thumbnail(self, stored: StoredImage) -> Path:
        thumbnail = self.thumbnail_path(stored.image.image_id)
        if thumbnail.is_file():
            return thumbnail

        original = self.original_path(stored)
        if not original.is_file():
            raise FileNotFoundError(original)
        try:
            with Image.open(original) as opened:
                image = ImageOps.exif_transpose(opened).convert("RGB")
                self._write_thumbnail(image, thumbnail)
        except (UnidentifiedImageError, OSError) as error:
            raise InvalidImageError("The stored image cannot be decoded.") from error
        return thumbnail

    def _write_thumbnail(self, image: Image.Image, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        rendered = image.copy()
        rendered.thumbnail(
            (self.thumbnail_max_size, self.thumbnail_max_size),
            Image.Resampling.LANCZOS,
        )
        temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
        try:
            rendered.save(
                temporary,
                format="WEBP",
                quality=self.thumbnail_quality,
                method=4,
            )
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
