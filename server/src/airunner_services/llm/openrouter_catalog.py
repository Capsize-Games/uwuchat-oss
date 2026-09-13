"""OpenRouter model catalog sync.

Fetches model pricing and metadata from the public OpenRouter API and
upserts into the ``public.openrouter_model`` table.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"

# ------------------------------------------------------------------
# Pinned-provider pricing overrides
# ------------------------------------------------------------------
# When a model is deliberately pinned to a specific provider by
# _provider_order_for_model() in
# ``airunner_services.cloud.llm.model_builders``, OpenRouter's
# blended default price (returned by the catalog API) may differ from
# the actual per-token rate charged by that pinned provider.  Entries
# here protect the *effective* price from being silently overwritten
# on every catalog sync.
#
# Only add entries whose real pinned-provider price *differs* from
# OpenRouter's blended default.  Adding a new non-default provider
# pin in model_builders.py?  Check whether an entry belongs here too.
PINNED_PROVIDER_PRICING: dict[str, dict[str, float]] = {
    # deepseek/* models are pinned to the native "deepseek" provider
    # (see _provider_order_for_model in cloud/llm/model_builders.py
    # and DEEPSEEK_V4_FLASH_MODEL in conf/model_settings.py for why —
    # 2026-08-20, moved off DeepInfra). DeepSeek's own API prices by
    # UTC time-of-day: these are the off-peak rates (UTC 10:00-01:00);
    # peak hours (UTC 01:00-04:00 and 06:00-10:00) are exactly 2x.
    # This entry deliberately does not model that swing — it exists
    # only to stop the blended OR default from silently understating
    # cost in margin analysis.
    "deepseek/deepseek-v4-flash-0731": {
        "input": 0.22,
        "output": 0.66,
        "cache": 0.007,
    },
}


def sync_catalog() -> int:
    """Fetch all models from OpenRouter and upsert them into the DB.

    Never raises — returns 0 on failure.
    """
    try:
        import requests
    except ImportError:
        logger.warning("requests not available; skipping OpenRouter sync")
        return 0

    try:
        resp = requests.get(OPENROUTER_MODELS_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("OpenRouter catalog sync failed: %s", exc)
        return 0

    models = data.get("data", [])
    if not models:
        return 0

    try:
        from airunner_services.database.models.openrouter_model import (
            OpenRouterModel,
        )
    except Exception:
        logger.warning(
            "OpenRouterModel not available; skipping sync"
        )
        return 0

    count = 0
    for entry in models:
        try:
            _upsert_model(entry)
            count += 1
        except Exception as exc:
            logger.debug(
                "Failed to upsert OpenRouter model %s: %s",
                entry.get("id", "?"),
                exc,
            )
    logger.info(
        "OpenRouter catalog synced: %d models upserted", count
    )
    return count


def _upsert_model(entry: dict) -> None:
    """Insert or update one OpenRouter model row.

    For models listed in *PINNED_PROVIDER_PRICING* the three price
    fields are set from the override table instead of the API
    ``pricing`` dict — the remainder of the row (display name,
    context length, providers_json, fetched_at) still updates
    normally from the live API response on every sync.
    """
    from datetime import datetime

    from airunner_services.database.models.openrouter_model import (
        OpenRouterModel,
    )

    model_id = str(entry.get("id", ""))
    if not model_id:
        return
    pricing = entry.get("pricing") or {}
    existing = (
        OpenRouterModel.objects.query()
        .filter(OpenRouterModel.model_id == model_id)
        .first()
    )

    override = PINNED_PROVIDER_PRICING.get(model_id)
    if override is not None:
        input_price = override["input"]
        output_price = override["output"]
        cache_price = override["cache"]
    else:
        input_price = (
            float(pricing.get("prompt", "0")) * 1_000_000
        )
        output_price = (
            float(pricing.get("completion", "0")) * 1_000_000
        )
        # OpenRouter uses "input_cache_read" (not "cache_read").
        cache_price = (
            float(pricing.get("input_cache_read", "0"))
            * 1_000_000
        )

    if existing:
        OpenRouterModel.objects.update(
            existing.id,
            display_name=str(entry.get("name", model_id)),
            input_price_per_mtok=input_price,
            output_price_per_mtok=output_price,
            cache_read_per_mtok=cache_price,
            context_length=int(entry.get("context_length") or 0),
            providers_json=entry.get("providers", []),
            fetched_at=datetime.utcnow(),
        )
    else:
        OpenRouterModel.objects.create(
            model_id=model_id,
            display_name=str(entry.get("name", model_id)),
            input_price_per_mtok=input_price,
            output_price_per_mtok=output_price,
            cache_read_per_mtok=cache_price,
            context_length=int(entry.get("context_length") or 0),
            providers_json=entry.get("providers", []),
            fetched_at=datetime.utcnow(),
        )


def get_model(model_id: str) -> Optional:
    """Return the DB row for *model_id*, or None."""
    try:
        from airunner_services.database.models.openrouter_model import (
            OpenRouterModel,
        )

        return (
            OpenRouterModel.objects.query()
            .filter(OpenRouterModel.model_id == model_id)
            .first()
        )
    except Exception:
        return None


def list_models() -> list:
    """Return all cached models sorted by cheapest input first."""
    try:
        from airunner_services.database.models.openrouter_model import (
            OpenRouterModel,
        )

        return (
            OpenRouterModel.objects.query()
            .order_by(
                OpenRouterModel.input_price_per_mtok.asc()
            )
            .all()
        )
    except Exception:
        return []
