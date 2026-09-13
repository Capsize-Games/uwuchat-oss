"""Service-owned torch-device helper."""

from __future__ import annotations

try:
    import torch
except ImportError:
    torch = None


def get_torch_device(card_index: int = 0):
    """Return the preferred torch device for one card index."""
    if torch is None:
        raise RuntimeError(
            "PyTorch is not available in this environment. "
            "get_torch_device is only supported in edge deployments."
        )
    use_cuda = torch.cuda.is_available()
    if not use_cuda:
        print("WARNING: CUDA NOT AVAILABLE, USING CPU")
    return torch.device(f"cuda:{card_index}" if use_cuda else "cpu")


__all__ = ["get_torch_device"]
