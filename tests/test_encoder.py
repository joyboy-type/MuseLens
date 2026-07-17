from types import SimpleNamespace

import torch

from muselens.encoder import feature_tensor


def test_feature_tensor_accepts_legacy_tensor_output() -> None:
    tensor = torch.ones(2, 3)
    assert feature_tensor(tensor) is tensor


def test_feature_tensor_extracts_transformers_5_pooler_output() -> None:
    pooled = torch.ones(2, 3)
    output = SimpleNamespace(pooler_output=pooled)
    assert feature_tensor(output) is pooled
