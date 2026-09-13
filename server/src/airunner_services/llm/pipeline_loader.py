"""Pipeline config loader.

Merges ``PIPELINE_DEFAULTS`` (framework) with a project's
``PIPELINE_CONFIG`` (from ``projects.<project>.server.ai_pipeline``).
Results are cached after first load; call ``reload_pipeline()`` to bust
the cache (needed when DB overrides are introduced in Phase 2).

Public API
----------
pipeline_config(key)   -> full merged dict for one pipeline key
pipeline_model(key)    -> model name string or None
pipeline_provider(key) -> provider string (default "local")
is_enabled(key)        -> bool
reload_pipeline()      -> bust cache (for DB override hot-reload)
"""

from __future__ import annotations

import importlib
import os
from copy import deepcopy
from typing import Any, Dict, Optional

from airunner_services.llm.pipeline_defaults import PIPELINE_DEFAULTS

from airunner_services.contract_enums import ModelService

_cache: Optional[Dict[str, Any]] = None


def _active_project() -> str:
    project = os.environ.get("AIRUNNER_PROJECT", "")
    if project:
        return project
    try:
        from airunner_services.conf import settings
        return getattr(settings, "AIRUNNER_PROJECT", "") or ""
    except Exception:
        return ""


def _load_project_config() -> dict:
    """Import PIPELINE_CONFIG from the active project module."""
    project = _active_project()
    if not project:
        return {}
    for module_path in (
        f"projects.{project}.server.ai_pipeline",
        f"projects.{project}.server.llm_routing",
    ):
        try:
            mod = importlib.import_module(module_path)
            cfg = getattr(mod, "PIPELINE_CONFIG", None) or getattr(
                mod, "MODEL_ROUTING", None
            )
            if isinstance(cfg, dict):
                return cfg
        except ImportError:
            continue
    return {}


def _merge(base: dict, override: dict) -> dict:
    """Deep-merge *override* into *base* (override wins on conflicts)."""
    result = deepcopy(base)
    for key, val in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(val, dict)
        ):
            result[key] = _merge(result[key], val)
        else:
            result[key] = deepcopy(val)
    return result


def _load_db_overrides() -> dict:
    """Load pipeline overrides from the DB (public schema).

    Never raises; returns {} when the table is missing or a query fails.
    This keeps pipeline_loader importable during early startup before
    the DB is ready.
    """
    try:
        from airunner_services.database.models.pipeline_config import (
            PipelineConfig,
        )

        rows = PipelineConfig.objects.query().all()
        result: dict = {}
        for row in rows:
            key = getattr(row, "pipeline_key", None)
            overrides = getattr(row, "overrides", None)
            if key and overrides and isinstance(overrides, dict):
                result[key] = overrides
        return result
    except Exception:
        return {}


def load_pipeline() -> Dict[str, Any]:
    """Return the merged pipeline config, cached after first call.

    Merge order (last wins): framework defaults → project overrides →
    DB overrides.
    """
    global _cache
    if _cache is None:
        merged = _merge(PIPELINE_DEFAULTS, _load_project_config())
        db_overrides = _load_db_overrides()
        for key, overrides in db_overrides.items():
            if key in merged and overrides:
                merged[key] = _merge(merged[key], overrides)
        _cache = merged
    return _cache


def reload_pipeline() -> Dict[str, Any]:
    """Bust the cache and reload from source."""
    global _cache
    _cache = None
    return load_pipeline()


def pipeline_config(key: str) -> Dict[str, Any]:
    """Return the merged config dict for a single pipeline key."""
    return load_pipeline().get(key, {})


def pipeline_model(key: str) -> Optional[str]:
    """Return the model name for *key*, or None."""
    return pipeline_config(key).get("model")


def pipeline_provider(key: str) -> str:
    """Return the provider string for *key*."""
    return pipeline_config(key).get("provider", ModelService.LOCAL.value)


def is_enabled(key: str) -> bool:
    """Return whether the pipeline key is enabled."""
    return bool(pipeline_config(key).get("enabled", True))


__all__ = [
    "pipeline_config",
    "pipeline_model",
    "pipeline_provider",
    "is_enabled",
    "load_pipeline",
    "reload_pipeline",
]
