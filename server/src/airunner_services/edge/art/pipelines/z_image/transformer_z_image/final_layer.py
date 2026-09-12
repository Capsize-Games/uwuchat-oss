"""Z-Image final output layer module."""

import torch.nn as nn

from airunner_services.edge.art.pipelines.z_image.transformer_z_image.constants import (
    ADALN_EMBED_DIM,
)


class FinalLayer(nn.Module):
    """Final normalization and projection layer of the transformer."""

    def __init__(self, hidden_size, out_channels):
        super().__init__()
        self.norm_final = nn.LayerNorm(
            hidden_size, elementwise_affine=False, eps=1e-6
        )
        self.linear = nn.Linear(hidden_size, out_channels, bias=True)
        self.adaLN_modulation = nn.Sequential(
            nn.SiLU(),
            nn.Linear(
                min(hidden_size, ADALN_EMBED_DIM), hidden_size, bias=True
            ),
        )

    def forward(self, x, c):
        scale = 1.0 + self.adaLN_modulation(c)
        x = self.norm_final(x) * scale.unsqueeze(1)
        x = self.linear(x)
        return x
