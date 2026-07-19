from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from .encoder import ClipEncoder
from .duplicates import VisualFingerprint, duplicate_components, hash_distance, visual_fingerprint
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


@dataclass(frozen=True)
class DuplicateMember:
    stored: StoredImage
    distance_to_representative: int
    recommended_keep: bool


@dataclass(frozen=True)
class DuplicateGroup:
    group_id: str
    members: list[DuplicateMember]
    potential_savings_bytes: int


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

    def backfill_dimensions(self) -> int:
        """Populate dimensions for libraries created before metadata filtering existed."""
        updated = 0
        for stored in self.repository.list_stored():
            if stored.width > 0 and stored.height > 0:
                continue
            original = self.original_path(stored)
            if not original.is_file():
                continue
            try:
                with Image.open(original) as opened:
                    width, height = ImageOps.exif_transpose(opened).size
            except (UnidentifiedImageError, OSError):
                continue
            self.repository.update_dimensions(stored.image.image_id, width, height)
            updated += 1
        return updated

    def backfill_visual_fingerprints(self) -> int:
        updated = 0
        for stored in self.repository.list_stored():
            if stored.perceptual_hash and stored.average_color:
                continue
            original = self.original_path(stored)
            if not original.is_file():
                continue
            try:
                with Image.open(original) as opened:
                    fingerprint = visual_fingerprint(ImageOps.exif_transpose(opened).convert("RGB"))
            except (UnidentifiedImageError, OSError):
                continue
            self.repository.update_visual_fingerprint(
                stored.image.image_id,
                fingerprint.perceptual_hash,
                fingerprint.average_color,
            )
            updated += 1
        return updated

    def duplicate_groups(
        self,
        *,
        max_hash_distance: int = 8,
        max_color_distance: float = 45,
    ) -> list[DuplicateGroup]:
        stored_images = self.repository.list_stored()
        fingerprints = [
            VisualFingerprint(stored.perceptual_hash, stored.average_color)
            for stored in stored_images
        ]
        groups: list[DuplicateGroup] = []
        for positions in duplicate_components(
            fingerprints,
            max_hash_distance=max_hash_distance,
            max_color_distance=max_color_distance,
        ):
            candidates = [stored_images[position] for position in positions]
            representative = max(
                enumerate(candidates),
                key=lambda item: (
                    item[1].width * item[1].height,
                    item[1].size_bytes,
                    -item[0],
                ),
            )[1]
            members = [
                DuplicateMember(
                    stored=stored,
                    distance_to_representative=hash_distance(
                        representative.perceptual_hash,
                        stored.perceptual_hash,
                    ),
                    recommended_keep=stored.image.image_id == representative.image.image_id,
                )
                for stored in candidates
            ]
            members.sort(key=lambda member: (not member.recommended_keep, member.stored.created_at))
            groups.append(
                DuplicateGroup(
                    group_id=min(stored.image.image_id for stored in candidates),
                    members=members,
                    potential_savings_bytes=sum(stored.size_bytes for stored in candidates)
                    - representative.size_bytes,
                )
            )
        groups.sort(key=lambda group: group.potential_savings_bytes, reverse=True)
        return groups

    def delete_imported_copy(self, image_id: str) -> StoredImage:
        stored = self.repository.find_by_id(image_id)
        if stored is None:
            raise KeyError(image_id)
        original = self.original_path(stored)
        thumbnail = self.thumbnail_path(image_id)
        if not self.repository.delete(image_id):
            raise KeyError(image_id)
        self.index.remove(image_id)
        original.unlink(missing_ok=True)
        thumbnail.unlink(missing_ok=True)
        return stored

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
        fingerprint = visual_fingerprint(candidate.image)
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
            width=candidate.image.width,
            height=candidate.image.height,
            created_at=datetime.now(timezone.utc).isoformat(),
            perceptual_hash=fingerprint.perceptual_hash,
            average_color=fingerprint.average_color,
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
