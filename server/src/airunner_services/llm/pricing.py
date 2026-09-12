"""Shared pricing lookups and cost computation.

Extracted from :mod:`airunner_services.api.routes.token_usage_routes`
so both the write path (:mod:`airunner_services.llm.token_usage`) and
the read path (admin RPCs) compute cost the same way.
"""

from __future__ import annotations

import logging

_log = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Module-level guards to avoid hammering the OpenRouter API with
# repeated fetches for the same missing / deprecated model.
# ------------------------------------------------------------------
_fetch_failed: set = set()
"""Model IDs not found in the OpenRouter catalog (deprecated/removed)."""

_fetch_in_flight: set = set()
"""Model IDs currently being fetched (prevents concurrent duplicates)."""


def compute_cost_usd(
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
    input_price: float,
    output_price: float,
    cache_price: float,
) -> float:
    """Return USD cost from token counts and per-million-token prices."""
    return (
        (input_tokens / 1_000_000) * input_price
        + (output_tokens / 1_000_000) * output_price
        + (cache_read_tokens / 1_000_000) * cache_price
    )


def _query_cache(model_id: str) -> dict | None:
    """Return {input, output, cache} from local cache, or None."""
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


def _cache_has_nonzero(model_id: str) -> bool:
    """True when *model_id* is in cache with non-zero pricing."""
    p = _query_cache(model_id)
    return p is not None and (p["input"] > 0 or p["output"] > 0)


def _alternate_ids(model_id: str) -> list[str]:
    """Return alternative model ID variants (hyphen/dot swaps)."""
    import re

    variants = []
    m = re.match(r"^(.+)-(\d+)-(\d+)$", model_id)
    if m:
        variants.append(f"{m.group(1)}-{m.group(2)}.{m.group(3)}")
        return variants
    m = re.match(r"^(.+)-(\d+)\.(\d+)$", model_id)
    if m:
        variants.append(f"{m.group(1)}-{m.group(2)}-{m.group(3)}")
    return variants


def _fetch_catalog(model_id: str) -> None:
    """Fetch the full OpenRouter catalog and upsert all models."""
    try:
        import requests
    except ImportError:
        _log.warning(
            "requests not available; cannot fetch model %s", model_id
        )
        return

    url = "https://openrouter.ai/api/v1/models"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        _log.warning(
            "Failed to fetch OpenRouter catalog for %s: %s",
            model_id, exc,
        )
        return

    models = data.get("data", []) if isinstance(data, dict) else []
    if not models:
        _log.warning("OpenRouter catalog returned empty model list")
        return

    found = False
    try:
        from airunner_services.llm.openrouter_catalog import (
            _upsert_model,
        )

        for m in models:
            if not isinstance(m, dict):
                continue
            mid = m.get("id", "")
            if not mid:
                continue
            try:
                _upsert_model(m)
            except Exception:
                pass
            if mid == model_id:
                found = True
    except Exception as exc:
        _log.warning("Failed to upsert catalog entries: %s", exc)

    if not found:
        _log.warning(
            "Model %s not found in OpenRouter catalog "
            "(may be deprecated or removed)",
            model_id,
        )
        _fetch_failed.add(model_id)
        _insert_placeholder(model_id)
        return

    _log.info(
        "Fetched and cached pricing for %s from OpenRouter "
        "(%d models upserted)",
        model_id, len(models),
    )


def _insert_placeholder(model_id: str) -> None:
    """Insert a zero-price placeholder so subsequent lookups avoid
    repeated HTTP fetches for models that no longer exist upstream."""
    try:
        from datetime import datetime

        from airunner_services.database.models.openrouter_model import (
            OpenRouterModel,
        )

        existing = (
            OpenRouterModel.objects.query()
            .filter(OpenRouterModel.model_id == model_id)
            .first()
        )
        if existing is not None:
            return
        OpenRouterModel.objects.create(
            model_id=model_id,
            display_name=f"{model_id} (deprecated/not found)",
            input_price_per_mtok=0,
            output_price_per_mtok=0,
            cache_read_per_mtok=0,
            context_length=0,
            providers_json=[],
            fetched_at=datetime.utcnow(),
        )
    except Exception:
        pass


def lookup_pricing(model_id: str) -> dict:
    """Return {input, output, cache} pricing for *model_id*.

    Falls back to the full OpenRouter catalog fetch on cache miss
    so cost estimates are never silently zero.  Returns an empty dict
    when all resolution paths fail.
    """
    # Fast path: exact match in cache
    p = _query_cache(model_id)
    if p is not None:
        if p["input"] > 0 or p["output"] > 0:
            return p
        for alt in _alternate_ids(model_id):
            alt_p = _query_cache(alt)
            if alt_p is not None and (
                alt_p["input"] > 0 or alt_p["output"] > 0
            ):
                return alt_p
        return p

    # Not in local cache — check dedup guards
    if model_id in _fetch_failed:
        for alt in _alternate_ids(model_id):
            if _cache_has_nonzero(alt):
                return _query_cache(alt) or {}
        return {}
    if model_id in _fetch_in_flight:
        return {}

    _fetch_in_flight.add(model_id)
    try:
        _log.warning(
            "Model %s not in openrouter_model cache; "
            "fetching from OpenRouter API",
            model_id,
        )
        _fetch_catalog(model_id)

        p2 = _query_cache(model_id)
        if p2 is not None:
            if p2["input"] > 0 or p2["output"] > 0:
                return p2
            for alt in _alternate_ids(model_id):
                alt_p = _query_cache(alt)
                if alt_p is not None and (
                    alt_p["input"] > 0 or alt_p["output"] > 0
                ):
                    return alt_p
            return p2
    except Exception:
        pass
    finally:
        _fetch_in_flight.discard(model_id)

    for alt in _alternate_ids(model_id):
        if _cache_has_nonzero(alt):
            return _query_cache(alt) or {}
    return {}


def price_lookup_bulk() -> dict[str, dict[str, float]]:
    """Return {model_id: {input, output, cache}} for all cached models.

    Only includes models with non-zero pricing.
    """
    try:
        from airunner_services.database.models.openrouter_model import (
            OpenRouterModel,
        )

        rows = OpenRouterModel.objects.query().all()
        result: dict[str, dict[str, float]] = {}
        for r in rows:
            inp = float(
                getattr(r, "input_price_per_mtok", 0) or 0
            )
            out = float(
                getattr(r, "output_price_per_mtok", 0) or 0
            )
            if inp == 0 and out == 0:
                continue
            mid = str(getattr(r, "model_id", ""))
            result[mid] = {
                "input": inp,
                "output": out,
                "cache": float(
                    getattr(r, "cache_read_per_mtok", 0) or 0
                ),
            }
        return result
    except Exception:
        return {}
