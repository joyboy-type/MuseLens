"""Reusable helpers for public deployment smoke tests."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from uuid import uuid4


TEMPORARY_GALLERY_CATEGORIES = ("dog", "car", "pizza")


@dataclass(frozen=True)
class UploadAsset:
    category: str
    path: Path
    upload_name: str


def select_upload_assets(manifest_path: Path) -> list[UploadAsset]:
    manifest = json.loads(manifest_path.read_text())
    assets = []
    for category in TEMPORARY_GALLERY_CATEGORIES:
        record = next(
            image for image in manifest["images"] if category in image["categories"]
        )
        assets.append(
            UploadAsset(
                category=category,
                path=manifest_path.parent / "images" / record["stored_filename"],
                upload_name=f"deployment-{category}.jpg",
            )
        )
    return assets


def multipart_files(assets: list[UploadAsset]) -> tuple[bytes, str]:
    boundary = f"muselens-{uuid4().hex}"
    body = bytearray()
    for asset in assets:
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(
            (
                'Content-Disposition: form-data; name="files"; '
                f'filename="{asset.upload_name}"\r\n'
            ).encode()
        )
        body.extend(b"Content-Type: image/jpeg\r\n\r\n")
        body.extend(asset.path.read_bytes())
        body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())
    return bytes(body), f"multipart/form-data; boundary={boundary}"
