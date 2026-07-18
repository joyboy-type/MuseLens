"""Optional high-precision multimodal reranking.

The message format and yes/no scoring follow the Apache-2.0 licensed reference
implementation from QwenLM/Qwen3-VL-Embedding.
"""

from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Any, Sequence

from .device import select_device
from .index import SearchHit


DEFAULT_INSTRUCTION = "Retrieve images relevant to the user's query."


def _nested_lists_to_tensors(inputs: Any, torch: Any) -> Any:
    """Bridge processor list fields that Transformers 5 expects as tensors."""
    for key, value in list(inputs.items()):
        if isinstance(value, list) and value and isinstance(value[0], list):
            inputs[key] = torch.tensor(value)
    return inputs


def rerank_candidates(
    query: str,
    candidates: Sequence[tuple[SearchHit, Any]],
    image_path_for: Any,
    scorer: Any,
    min_score: float,
    recall_k: int,
) -> list[tuple[SearchHit, Any]]:
    selected = list(candidates[:recall_k])
    paths = [image_path_for(stored) for _, stored in selected]
    available = [
        ((hit, stored), path)
        for (hit, stored), path in zip(selected, paths, strict=True)
        if path.is_file()
    ]
    scores = scorer.score(query, [path for _, path in available])
    ranked = sorted(
        [
            (SearchHit(hit.image, score), stored)
            for ((hit, stored), _), score in zip(available, scores, strict=True)
            if score >= min_score
        ],
        key=lambda item: item[0].score,
        reverse=True,
    )
    return ranked


class QwenVLReranker:
    """Lazy Qwen3-VL relevance scorer for text/image pairs."""

    def __init__(
        self,
        model_id: str = "Qwen/Qwen3-VL-Reranker-2B",
        instruction: str = DEFAULT_INSTRUCTION,
        max_pixels: int = 1280 * 32 * 32,
    ) -> None:
        self.model_id = model_id
        self.instruction = instruction
        self.max_pixels = max_pixels
        self.device = select_device()
        self.model: Any | None = None
        self.processor: Any | None = None
        self.score_linear: Any | None = None
        self._lock = RLock()

    @property
    def loaded(self) -> bool:
        return self.model is not None

    def load(self) -> None:
        with self._lock:
            if self.loaded:
                return
            import torch
            from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

            dtype = torch.bfloat16 if self.device.type in {"mps", "cuda"} else torch.float32
            language_model = Qwen3VLForConditionalGeneration.from_pretrained(
                self.model_id,
                torch_dtype=dtype,
            )
            language_model.to(self.device).eval()
            self.processor = AutoProcessor.from_pretrained(
                self.model_id,
                padding_side="left",
            )
            yes_id = self.processor.tokenizer.get_vocab()["yes"]
            no_id = self.processor.tokenizer.get_vocab()["no"]
            yes_weight = language_model.lm_head.weight.data[yes_id]
            no_weight = language_model.lm_head.weight.data[no_id]
            score_linear = torch.nn.Linear(yes_weight.shape[0], 1, bias=False)
            with torch.no_grad():
                score_linear.weight[0] = yes_weight - no_weight
            self.model = language_model.model
            self.score_linear = score_linear.to(self.device, dtype=dtype).eval()

    def score(self, query: str, image_paths: Sequence[Path]) -> list[float]:
        if not image_paths:
            return []
        with self._lock:
            self.load()
            return [self._score_one(query, path) for path in image_paths]

    def _score_one(self, query: str, image_path: Path) -> float:
        import torch
        from qwen_vl_utils import process_vision_info

        messages = self._messages(query, image_path)
        batched_messages = [messages]
        text = self.processor.apply_chat_template(
            batched_messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        images, videos, video_kwargs = process_vision_info(
            batched_messages,
            image_patch_size=16,
            return_video_kwargs=True,
            return_video_metadata=True,
        )
        video_metadata = None
        if videos is not None:
            videos, video_metadata = zip(*videos, strict=True)
            videos, video_metadata = list(videos), list(video_metadata)
        inputs = self.processor(
            text=text,
            images=images,
            videos=videos,
            video_metadata=video_metadata,
            padding=True,
            return_tensors="pt",
            do_resize=False,
            **video_kwargs,
        )
        inputs = _nested_lists_to_tensors(inputs, torch).to(self.device)
        with torch.inference_mode():
            hidden = self.model(**inputs).last_hidden_state[:, -1]
            probability = torch.sigmoid(self.score_linear(hidden)).squeeze()
        return float(probability.detach().cpu())

    def _messages(self, query: str, image_path: Path) -> list[dict[str, Any]]:
        return [
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Judge whether the Document meets the requirements based on "
                            "the Query and the Instruct provided. Answer only yes or no."
                        ),
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"<Instruct>: {self.instruction}"},
                    {"type": "text", "text": f"<Query>: {query}"},
                    {"type": "text", "text": "\n<Document>:"},
                    {
                        "type": "image",
                        "image": image_path.resolve().as_uri(),
                        "min_pixels": 4 * 32 * 32,
                        "max_pixels": self.max_pixels,
                    },
                ],
            },
        ]
