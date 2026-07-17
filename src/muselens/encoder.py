from collections.abc import Sequence
from typing import Any

import numpy as np
from PIL import Image

from .device import select_device


def feature_tensor(output: Any) -> Any:
    """Support both tensor outputs and Transformers 5 pooled model outputs."""
    pooled = getattr(output, "pooler_output", None)
    return pooled if pooled is not None else output


class VisionLanguageEncoder:
    """Lazy Hugging Face adapter for CLIP-compatible vision-language models."""

    def __init__(self, model_id: str) -> None:
        self.model_id = model_id
        self.device = select_device()
        self.model: Any | None = None
        self.processor: Any | None = None

    @property
    def loaded(self) -> bool:
        return self.model is not None

    def load(self) -> None:
        if self.loaded:
            return
        from transformers import AutoModel, AutoProcessor

        self.processor = AutoProcessor.from_pretrained(self.model_id)
        self.model = AutoModel.from_pretrained(self.model_id).to(self.device).eval()

    def encode_images(self, images: Sequence[Image.Image]) -> np.ndarray:
        self.load()
        import torch

        inputs = self.processor(
            images=[image.convert("RGB") for image in images],
            return_tensors="pt",
        )
        model_inputs = {key: value.to(self.device) for key, value in inputs.items()}
        with torch.inference_mode():
            output = self.model.get_image_features(**model_inputs)
            features = feature_tensor(output)
        return features.cpu().numpy().astype(np.float32)
    def encode_texts(self, texts: Sequence[str]) -> np.ndarray:
        self.load()
        import torch

        inputs = self.processor(
            text=list(texts),
            return_tensors="pt",
            padding="max_length",
            truncation=True,
        )
        model_inputs = {key: value.to(self.device) for key, value in inputs.items()}
        with torch.inference_mode():
            output = self.model.get_text_features(**model_inputs)
            features = feature_tensor(output)
        return features.cpu().numpy().astype(np.float32)


# Backward-compatible name for existing imports and third-party examples.
ClipEncoder = VisionLanguageEncoder
