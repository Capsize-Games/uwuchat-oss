"""Tests that UwUchat pipeline routing never selects a local/edge path.

UwUchat is cloud-only — this is a guard against silent routing drift.

IMPORTANT: ``AIRUNNER_PROJECT=uwuchat`` must be set (via fixture) and
``reload_pipeline()`` called before each test so ``load_pipeline()``
reads UwUchat's actual merged config (project overrides + framework
defaults), not a stale cached result from a previous test or the
framework-only default.
"""

from __future__ import annotations

from airunner_services.conf.model_settings import MODEL_PROVIDER
import pytest
from airunner_services.contract_enums import ModelService


@pytest.fixture(autouse=True)
def _uwuchat_project(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure every test runs against the UwUchat pipeline config."""
    monkeypatch.setenv("AIRUNNER_PROJECT", "uwuchat")
    from airunner_services.llm.pipeline_loader import reload_pipeline

    reload_pipeline()


# ---------------------------------------------------------------------------
# Routing key checks — every key that exists in model_router's subset
# ---------------------------------------------------------------------------


def _load_uwuchat_pipeline() -> dict:
    from airunner_services.llm.pipeline_loader import load_pipeline

    return load_pipeline()


def test_pipeline_is_not_empty() -> None:
    """UwUchat pipeline config is non-empty (sanity check)."""
    pipeline = _load_uwuchat_pipeline()
    assert pipeline, "UwUchat pipeline must be non-empty"
    assert "DIALOGUE" in pipeline, "UwUchat pipeline must have DIALOGUE"


def test_dialogue_routing_subset_keys_not_local() -> None:
    """Every key in model_router's dialogue_routing_subset that exists
    in the pipeline must use openrouter, never local or empty."""
    from airunner_services.llm.model_router import (
        _dialogue_routing_subset,
    )

    pipeline = _load_uwuchat_pipeline()
    subset = _dialogue_routing_subset(pipeline)

    for key, rule in subset.items():
        provider = rule.get("provider", "")
        assert provider != ModelService.LOCAL.value, (
            f"UwUchat {key} routing must not select local provider"
        )
        assert provider == MODEL_PROVIDER, (
            f"UwUchat {key} routing must use openrouter; "
            f"got {provider!r}"
        )


def test_no_gguf_model_in_routing() -> None:
    """No UwUchat routing rule uses a GGUF model path."""
    from airunner_services.llm.model_router import (
        _dialogue_routing_subset,
    )

    pipeline = _load_uwuchat_pipeline()
    subset = _dialogue_routing_subset(pipeline)
    for key, rule in subset.items():
        model = rule.get("model", "")
        assert ".gguf" not in model.lower(), (
            f"{key} routing must not use GGUF: {model}"
        )
