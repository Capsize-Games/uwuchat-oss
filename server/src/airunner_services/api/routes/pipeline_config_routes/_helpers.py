"""Shared helpers for pipeline-config admin routes."""

from __future__ import annotations

from copy import deepcopy


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep-merge *override* into *base*, returning a new dict."""
    result = deepcopy(base)
    for key, val in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(val, dict)
        ):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = deepcopy(val)
    return result
