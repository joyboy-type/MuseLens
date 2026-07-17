from __future__ import annotations

import math

import torch
from torch import nn
from torch.nn import functional as F


class ResidualAdapter(nn.Module):
    """Small bottleneck adapter initialized as an identity mapping."""

    def __init__(
        self,
        embedding_dim: int,
        bottleneck_dim: int = 128,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        self.down = nn.Linear(embedding_dim, bottleneck_dim)
        self.up = nn.Linear(bottleneck_dim, embedding_dim)
        self.dropout = nn.Dropout(dropout)
        self.gate = nn.Parameter(torch.tensor(0.1))
        nn.init.zeros_(self.up.weight)
        nn.init.zeros_(self.up.bias)

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        residual = self.up(self.dropout(F.gelu(self.down(features))))
        return F.normalize(features + self.gate * residual, dim=-1)


class DualEncoderAdapter(nn.Module):
    """Separate lightweight adapters for frozen image and text embeddings."""

    def __init__(
        self,
        embedding_dim: int,
        bottleneck_dim: int = 128,
        dropout: float = 0.1,
        temperature: float = 0.07,
    ) -> None:
        super().__init__()
        self.image_adapter = ResidualAdapter(embedding_dim, bottleneck_dim, dropout)
        self.text_adapter = ResidualAdapter(embedding_dim, bottleneck_dim, dropout)
        self.logit_scale = nn.Parameter(torch.tensor(math.log(1.0 / temperature)))

    def adapt_images(self, features: torch.Tensor) -> torch.Tensor:
        return self.image_adapter(features)

    def adapt_texts(self, features: torch.Tensor) -> torch.Tensor:
        return self.text_adapter(features)

    def forward(
        self,
        image_features: torch.Tensor,
        text_features: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        return self.adapt_images(image_features), self.adapt_texts(text_features)


def symmetric_contrastive_loss(
    image_features: torch.Tensor,
    text_features: torch.Tensor,
    logit_scale: torch.Tensor,
) -> torch.Tensor:
    """CLIP-style in-batch contrastive loss for unique image-text pairs."""
    if image_features.shape != text_features.shape:
        raise ValueError("image and text feature batches must have matching shapes")
    if image_features.ndim != 2 or image_features.shape[0] < 2:
        raise ValueError("contrastive batches must contain at least two pairs")

    scale = logit_scale.exp().clamp(max=100.0)
    logits = scale * image_features @ text_features.T
    labels = torch.arange(logits.shape[0], device=logits.device)
    image_loss = F.cross_entropy(logits, labels)
    text_loss = F.cross_entropy(logits.T, labels)
    return (image_loss + text_loss) / 2
