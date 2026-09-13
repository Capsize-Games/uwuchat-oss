"""Z-Image rotary positional embedding helper."""

from typing import List

import torch


class RopeEmbedder:
    """Compute rotary positional embeddings for 3D coordinates."""

    def __init__(
        self,
        theta: float = 256.0,
        axes_dims: List[int] = (16, 56, 56),
        axes_lens: List[int] = (64, 128, 128),
    ):
        self.theta = theta
        self.axes_dims = axes_dims
        self.axes_lens = axes_lens
        assert len(axes_dims) == len(
            axes_lens
        ), "axes_dims and axes_lens must have the same length"
        self.freqs_cis = None

    @staticmethod
    def precompute_freqs_cis(
        dim: List[int], end: List[int], theta: float = 256.0
    ):
        with torch.device("cpu"):
            freqs_cis = []
            for i, (d, e) in enumerate(zip(dim, end)):
                freqs = 1.0 / (
                    theta
                    ** (
                        torch.arange(
                            0, d, 2, dtype=torch.float64, device="cpu"
                        )
                        / d
                    )
                )
                timestep = torch.arange(
                    e, device=freqs.device, dtype=torch.float64
                )
                freqs = torch.outer(timestep, freqs).float()
                freqs_cis_i = torch.polar(torch.ones_like(freqs), freqs).to(
                    torch.complex64
                )
                freqs_cis.append(freqs_cis_i)
            return freqs_cis

    def __call__(self, ids: torch.Tensor):
        assert ids.ndim == 2
        assert ids.shape[-1] == len(self.axes_dims)

        device = ids.device

        if self.freqs_cis is None:
            self.freqs_cis = self.precompute_freqs_cis(
                self.axes_dims, self.axes_lens, theta=self.theta
            )
            self.freqs_cis = [
                freqs_cis.to(device) for freqs_cis in self.freqs_cis
            ]
        else:
            # Ensure freqs_cis are on the same device as ids
            if self.freqs_cis[0].device != device:
                self.freqs_cis = [
                    freqs_cis.to(device) for freqs_cis in self.freqs_cis
                ]

        result = []
        for i in range(len(self.axes_dims)):
            index = ids[:, i]
            result.append(self.freqs_cis[i][index])
        return torch.cat(result, dim=-1)
