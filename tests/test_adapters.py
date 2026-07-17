import torch

from muselens.adapters import (
    DualEncoderAdapter,
    ResidualAdapter,
    symmetric_contrastive_loss,
)


def test_residual_adapter_starts_as_normalized_identity() -> None:
    adapter = ResidualAdapter(embedding_dim=4, bottleneck_dim=2, dropout=0.0)
    features = torch.tensor([[3.0, 4.0, 0.0, 0.0]])

    output = adapter(features)

    torch.testing.assert_close(output, torch.tensor([[0.6, 0.8, 0.0, 0.0]]))


def test_dual_adapter_preserves_shapes() -> None:
    adapter = DualEncoderAdapter(embedding_dim=8, bottleneck_dim=2)
    images, texts = adapter(torch.randn(3, 8), torch.randn(3, 8))

    assert images.shape == (3, 8)
    assert texts.shape == (3, 8)
    torch.testing.assert_close(images.norm(dim=-1), torch.ones(3))
    torch.testing.assert_close(texts.norm(dim=-1), torch.ones(3))


def test_contrastive_loss_rewards_aligned_pairs() -> None:
    features = torch.eye(4)
    scale = torch.tensor(2.0)

    aligned = symmetric_contrastive_loss(features, features, scale)
    reversed_pairs = symmetric_contrastive_loss(features, features.flip(0), scale)

    assert aligned < reversed_pairs


def test_adapter_checkpoint_round_trip(tmp_path) -> None:
    adapter = DualEncoderAdapter(embedding_dim=4, bottleneck_dim=2, dropout=0.0)
    checkpoint = {
        "state_dict": adapter.state_dict(),
        "model_id": "test-model",
        "embedding_dim": 4,
        "bottleneck_dim": 2,
        "epoch": 1,
        "validation": {"mrr": 0.5},
    }
    path = tmp_path / "adapter.pt"
    torch.save(checkpoint, path)

    restored = torch.load(path, map_location="cpu", weights_only=True)
    loaded = DualEncoderAdapter(embedding_dim=4, bottleneck_dim=2, dropout=0.0)
    loaded.load_state_dict(restored["state_dict"])

    features = torch.randn(3, 4)
    torch.testing.assert_close(adapter.adapt_images(features), loaded.adapt_images(features))
