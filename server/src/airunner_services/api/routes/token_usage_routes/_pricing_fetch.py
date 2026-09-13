"""OpenRouter pricing fetch and cache population."""

from __future__ import annotations

from typing import Any

from airunner_services.api.routes.token_usage_routes._pricing_cache import (
    _alternate_model_ids,
    _cache_has_nonzero_price,
    _fetch_failed,
    _fetch_in_flight,
    _lookup_pricing_in_cache,
)


def _ensure_model_in_cache(model_id: str) -> dict:
    """Return pricing for *model_id*, fetching from OpenRouter if missing.

    Never raises — returns an empty dict on failure.
    Module-level dedup prevents repeat fetches for deprecated models
    and concurrent duplicate requests.
    """
    # Fast path: exact match in cache
    p = _lookup_pricing_in_cache(model_id)
    if p is not None:
        if p["input"] > 0 or p["output"] > 0:
            return p
        # Exact match exists but has zero price — try alternates
        for alt in _alternate_model_ids(model_id):
            alt_p = _lookup_pricing_in_cache(alt)
            if alt_p is not None and (
                alt_p["input"] > 0 or alt_p["output"] > 0
            ):
                return alt_p
        return p  # all variants zero — return the zero-price entry

    # Not in local cache — check module-level guards
    if model_id in _fetch_failed:
        # Try alternate IDs even when exact match previously failed
        for alt in _alternate_model_ids(model_id):
            if _cache_has_nonzero_price(alt):
                return _lookup_pricing_in_cache(alt) or {}
        return {}
    if model_id in _fetch_in_flight:
        return {}

    _fetch_in_flight.add(model_id)
    try:
        import logging

        _log = logging.getLogger(__name__)
        _log.warning(
            "Model %s not in openrouter_model cache; "
            "fetching from OpenRouter API",
            model_id,
        )
        _do_fetch_single_model(model_id, _log)

        # Re-query after fetch
        p2 = _lookup_pricing_in_cache(model_id)
        if p2 is not None:
            if p2["input"] > 0 or p2["output"] > 0:
                return p2
            # Still zero after fetch — try alternates
            for alt in _alternate_model_ids(model_id):
                alt_p = _lookup_pricing_in_cache(alt)
                if alt_p is not None and (
                    alt_p["input"] > 0 or alt_p["output"] > 0
                ):
                    return alt_p
            return p2
    except Exception:
        pass
    finally:
        _fetch_in_flight.discard(model_id)

    # Last resort: try alternate IDs directly
    for alt in _alternate_model_ids(model_id):
        if _cache_has_nonzero_price(alt):
            return _lookup_pricing_in_cache(alt) or {}
    return {}


def _do_fetch_single_model(model_id: str, _log: Any) -> None:
    """Fetch the full OpenRouter catalog and search for *model_id*.

    OpenRouter does not expose a single-model GET endpoint — the
    per-model URL returns 404 for every model.  We fetch the full
    ``GET /api/v1/models`` list and search it instead.

    Every model in the response is upserted (not just the one we
    searched for) so a single catalog fetch populates the entire
    cache, preventing N separate downloads for N missing models.
    """
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
            model_id,
            exc,
        )
        return

    models = data.get("data", []) if isinstance(data, dict) else []
    if not models:
        _log.warning("OpenRouter catalog returned empty model list")
        return

    # Upsert every model from the response so subsequent lookups
    # hit the local cache instead of re-downloading the catalog.
    found = False
    try:
        from airunner_services.llm.openrouter_catalog import _upsert_model

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
        _log.warning(
            "Failed to upsert catalog entries: %s", exc
        )

    if not found:
        _log.warning(
            "Model %s not found in OpenRouter catalog "
            "(may be deprecated or removed)",
            model_id,
        )
        _fetch_failed.add(model_id)
        _insert_placeholder_model(model_id)
        return

    _log.info(
        "Fetched and cached pricing for %s from OpenRouter "
        "(%d models upserted)",
        model_id,
        len(models),
    )


def _insert_placeholder_model(model_id: str) -> None:
    """Insert a zero-price placeholder so the model is found in the
    local cache on subsequent lookups — even after server restart.

    This prevents repeated HTTP fetches of the full OpenRouter
    catalog for models that no longer exist upstream.
    """
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
            return  # already persisted (another process beat us)
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
