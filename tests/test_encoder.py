from types import SimpleNamespace

import numpy as np
import torch

from muselens.encoder import VisionLanguageEncoder, feature_tensor


def test_feature_tensor_accepts_legacy_tensor_output() -> None:
    tensor = torch.ones(2, 3)
    assert feature_tensor(tensor) is tensor


def test_feature_tensor_extracts_transformers_5_pooler_output() -> None:
    pooled = torch.ones(2, 3)
    output = SimpleNamespace(pooler_output=pooled)
    assert feature_tensor(output) is pooled


def test_text_embeddings_are_cached_by_query() -> None:
    class FakeProcessor:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(self, *, text, **_kwargs):
            self.calls += 1
            return {"input_ids": torch.tensor([[len(item), 1] for item in text])}

    class FakeModel:
        def get_text_features(self, *, input_ids):
            return input_ids.float()

    encoder = VisionLanguageEncoder("fake")
    encoder.device = torch.device("cpu")
    encoder.processor = FakeProcessor()
    encoder.model = FakeModel()

    first = encoder.encode_texts(["dog", "beach"])
    second = encoder.encode_texts(["dog"])

    assert encoder.processor.calls == 1
    np.testing.assert_array_equal(first[0], second[0])
