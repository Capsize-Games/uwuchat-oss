"""Pricing cache lookups for token usage cost estimation."""

from __future__ import annotations


# ------------------------------------------------------------------
# Module-level guards to avoid hammering the OpenRouter API with
# repeated fetches for the same missing / deprecated model.
# ------------------------------------------------------------------
_fetch_failed: set = set()
"""Model IDs not found in the OpenRouter catalog (deprecated/removed)."""

_fetch_in_flight: set = set()
"""Model IDs currently being fetched (prevents concurrent duplicates)."""


def _price_lookup() -> dict:
    """Return {model_id: {input_price, output_price, cache_price}}.

    Only includes models with non-zero pricing so that
    :func:`_compute_cost` falls through to :func:`_ensure_model_in_cache`
    (which handles alternate model-ID formats) for any model that has
    a zero-price placeholder in the local cache.
    """
    try:
        from airunner_services.database.models.openrouter_model import (
            OpenRouterModel,
        )

        rows = OpenRouterModel.objects.query().all()
        result: dict = {}
        for r in rows:
            inp = float(
                getattr(r, "input_price_per_mtok", 0) or 0
            )
            out = float(
                getattr(r, "output_price_per_mtok", 0) or 0
            )
            if inp == 0 and out == 0:
                continue  # zero placeholder — let _ensure_model_in_cache
            result[getattr(r, "model_id", "")] = {
                "input": inp,
                "output": out,
                "cache": float(
                    getattr(r, "cache_read_per_mtok", 0) or 0
                ),
            }
        return result
    except Exception:
        return {}


def _alternate_model_ids(model_id: str) -> list[str]:
    """Return alternative model ID variants that may resolve pricing.

    OpenRouter sometimes changes a model's ID (e.g. hyphen vs dot in
    version numbers like ``anthropic/claude-haiku-4-5`` vs
    ``anthropic/claude-haiku-4.5``).  This returns plausible variants
    to try when the exact *model_id* has zero or missing pricing.
    """
    import re

    variants = []
    # Swap hyphens and dots in the last version-number segment:
    #   anthropic/claude-haiku-4-5  →  anthropic/claude-haiku-4.5
    #   anthropic/claude-haiku-4.5  →  anthropic/claude-haiku-4-5
    m = re.match(r"^(.+)-(\d+)-(\d+)$", model_id)
    if m:
        variants.append(f"{m.group(1)}-{m.group(2)}.{m.group(3)}")
        return variants
    m = re.match(r"^(.+)-(\d+)\.(\d+)$", model_id)
    if m:
        variants.append(f"{m.group(1)}-{m.group(2)}-{m.group(3)}")
    return variants


def _lookup_pricing_in_cache(model_id: str) -> dict | None:
    """Return pricing dict for *model_id* from local cache, or None."""
    try:
        from airunner_services.database.models.openrouter_model import (
            OpenRouterModel,
        )

        row = (
            OpenRouterModel.objects.query()
            .filter(OpenRouterModel.model_id == model_id)
            .first()
        )
        if row is None:
            return None
        inp = float(getattr(row, "input_price_per_mtok", 0) or 0)
        out = float(getattr(row, "output_price_per_mtok", 0) or 0)
        cache = float(getattr(row, "cache_read_per_mtok", 0) or 0)
        return {"input": inp, "output": out, "cache": cache}
    except Exception:
        return None


def _cache_has_nonzero_price(model_id: str) -> bool:
    """True when *model_id* is in cache with non-zero pricing."""
    p = _lookup_pricing_in_cache(model_id)
    return p is not None and (p["input"] > 0 or p["output"] > 0)
