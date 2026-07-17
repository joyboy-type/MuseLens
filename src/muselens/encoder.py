from collections import OrderedDict
from collections.abc import Sequence
from threading import RLock
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
        self._inference_lock = RLock()
        self._text_cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._text_cache_size = 100

    @property
    def loaded(self) -> bool:
        return self.model is not None

    def load(self) -> None:
        with self._inference_lock:
            if self.loaded:
                return
            from transformers import AutoModel, AutoProcessor

            self.processor = AutoProcessor.from_pretrained(self.model_id)
            self.model = AutoModel.from_pretrained(self.model_id).to(self.device).eval()

    def encode_images(self, images: Sequence[Image.Image]) -> np.ndarray:
        with self._inference_lock:
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
        if not texts:
            return np.empty((0, 0), dtype=np.float32)
        with self._inference_lock:
            missing = list(dict.fromkeys(text for text in texts if text not in self._text_cache))
            if missing:
                self.load()
                import torch

                inputs = self.processor(
                    text=missing,
                    return_tensors="pt",
                    padding="max_length",
                    truncation=True,
                )
                model_inputs = {key: value.to(self.device) for key, value in inputs.items()}
                with torch.inference_mode():
                    output = self.model.get_text_features(**model_inputs)
                    features = feature_tensor(output)
                vectors = features.cpu().numpy().astype(np.float32)
                for text, vector in zip(missing, vectors, strict=True):
                    self._text_cache[text] = vector.copy()
                    self._text_cache.move_to_end(text)
                    if len(self._text_cache) > self._text_cache_size:
                        self._text_cache.popitem(last=False)
            for text in texts:
                self._text_cache.move_to_end(text)
            return np.stack([self._text_cache[text].copy() for text in texts])


# Backward-compatible name for existing imports and third-party examples.
ClipEncoder = VisionLanguageEncoder
