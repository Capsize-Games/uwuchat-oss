"""Pipeline env-provider tests (work item W3).

``AIRUNNER_LLM_PROVIDER`` / ``AIRUNNER_LLM_MODEL`` must override the
provider/model of every *text-generation* pipeline in the project
``ai_pipeline.py`` files (UwUchat and Headlesscode) while the
``EMBEDDING`` entry stays pinned to the cloud provider, and defaults
must be byte-identical when the env vars are unset.

The module-level ``PROVIDER``/``DIALOGUE_MODEL`` constants are resolved
from ``os.getenv`` at import time, so each test re-imports the pipeline
module after setting/clearing the env vars.  ``reload_pipeline()``
busts the loader cache between tests so ``load_pipeline()`` re-reads
the project module.
"""

from __future__ import annotations

import importlib
import os
from collections.abc import Iterator

import pytest
from airunner_services.conf.model_settings import (
    DEEPSEEK_V4_FLASH_MODEL,
    MODEL_PROVIDER,
    QWEN_EMBEDDING_MODEL,
)
from airunner_services.contract_enums import ModelService

# Every text-generation pipeline that must honor the env override
# (per plans/lan-shared-edge-inference.md, work item W3).
TEXT_PIPELINE_KEYS = (
    "DIALOGUE",
    "PROMPT_REWRITE",
    "TOOL_CLASSIFICATION",
    "TOOL_EXECUTION",
    "SUMMARIZATION",
    "STATELESS",
    "CHARACTER_CREATION",
    "KNOWLEDGE",
    "INTRA_SESSION_MOOD",
    "ROLLING_COMPRESSOR",
    "EPISODIC_SUMMARIZER",
    "MEMORY_UPDATER",
    "NODE_VALIDATOR",
    "CURIOSITY_ENGINE",
    "JOURNAL_SUMMARIZER",
)

PROJECTS = ("uwuchat", "headlesscode")

OLLAMA = ModelService.OLLAMA.value
OPENROUTER = ModelService.OPENROUTER.value
LOCAL = ModelService.LOCAL.value

OVERRIDE_MODEL = "qwen3.5-9b-q8_0"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear the override env vars so defaults are exercised."""
    monkeypatch.delenv("AIRUNNER_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("AIRUNNER_LLM_MODEL", raising=False)


@pytest.fixture()
def _ollama_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set the override env vars to the LAN-stack values."""
    monkeypatch.setenv("AIRUNNER_LLM_PROVIDER", OLLAMA)
    monkeypatch.setenv("AIRUNNER_LLM_MODEL", OVERRIDE_MODEL)


def _module(project: str):
    """Import the project's ai_pipeline module."""
    return importlib.import_module(
        f"projects.{project}.server.ai_pipeline"
    )


def _reload_module(project: str):
    """Re-import the module so module-level env constants re-resolve."""
    module = _module(project)
    importlib.reload(module)
    return module


def _set_project(project: str) -> None:
    """Point the pipeline loader at *project*."""
    os.environ["AIRUNNER_PROJECT"] = project


def _configured_text_entries(project: str) -> Iterator[tuple]:
    """Yield (key, entry) for every text pipeline present in the
    project's PIPELINE_CONFIG (DIALOGUE's tiers are flattened in)."""
    config = _module(project).PIPELINE_CONFIG
    for key in TEXT_PIPELINE_KEYS:
        entry = config.get(key)
        if entry is None:
            continue
        if key == "DIALOGUE":
            yield key, entry
            for tier in entry.get("tiers", []):
                yield f"{key}/tier/{tier['name']}", tier
        else:
            yield key, entry


def _assert_text_entries(project: str, provider: str, model: str) -> None:
    """Assert every text pipeline in *project* resolves to provider/model."""
    from airunner_services.llm.pipeline_loader import (
        load_pipeline,
        reload_pipeline,
    )

    # Re-import first: the module may already be cached in sys.modules
    # from an earlier test with different env vars.
    _reload_module(project)
    _set_project(project)
    reload_pipeline()
    pipeline = load_pipeline()
    for key, entry in _configured_text_entries(project):
        if key.startswith("DIALOGUE/tier/"):
            # Tiers inherit the provider from the DIALOGUE root; only
            # the model is overridden per tier.
            assert entry["model"] == model, (
                f"{project} {key} model must be {model!r}, "
                f"got {entry['model']!r}"
            )
            continue
        assert entry["provider"] == provider, (
            f"{project} {key} provider must be {provider!r}, "
            f"got {entry['provider']!r}"
        )
        assert entry["model"] == model, (
            f"{project} {key} model must be {model!r}, "
            f"got {entry['model']!r}"
        )
        root_key = key.split("/")[0]
        assert pipeline[root_key].get("provider") == provider, (
            f"{project} merged {root_key} provider must be {provider!r}"
        )


def _assert_embedding_pinned(project: str) -> None:
    """Assert the EMBEDDING entry stays cloud-pinned to the qwen model."""
    entry = _module(project).PIPELINE_CONFIG.get("EMBEDDING")
    if entry is None:
        return
    assert entry["provider"] == MODEL_PROVIDER, (
        f"{project} EMBEDDING must stay {MODEL_PROVIDER!r}, "
        f"got {entry['provider']!r}"
    )
    assert entry["model"] == QWEN_EMBEDDING_MODEL, (
        f"{project} EMBEDDING must stay {QWEN_EMBEDDING_MODEL!r}, "
        f"got {entry['model']!r}"
    )


def _assert_defaults_unchanged(project: str) -> None:
    """Assert the unset-env defaults match the framework constants."""
    module = _reload_module(project)
    assert module.PROVIDER == MODEL_PROVIDER, (
        f"{project} PROVIDER default must be {MODEL_PROVIDER!r}"
    )
    assert module.DIALOGUE_MODEL == DEEPSEEK_V4_FLASH_MODEL, (
        f"{project} DIALOGUE_MODEL default must be "
        f"{DEEPSEEK_V4_FLASH_MODEL!r}"
    )
    _assert_text_entries(project, OPENROUTER, DEEPSEEK_V4_FLASH_MODEL)


def test_uwuchat_defaults_are_cloud_when_env_unset() -> None:
    """UwUchat pipeline resolves to openrouter/deepseek-v4-flash."""
    _assert_defaults_unchanged("uwuchat")


def test_headlesscode_defaults_are_cloud_when_env_unset() -> None:
    """Headlesscode pipeline resolves to openrouter/deepseek-v4-flash."""
    _assert_defaults_unchanged("headlesscode")


def test_uwuchat_ollama_override_applies_to_all_text_pipelines(
    _ollama_env,
) -> None:
    """Every UwUchat text pipeline honors the ollama override."""
    _assert_text_entries("uwuchat", OLLAMA, OVERRIDE_MODEL)


def test_headlesscode_ollama_override_applies_to_all_text_pipelines(
    _ollama_env,
) -> None:
    """Every Headlesscode text pipeline honors the ollama override."""
    _assert_text_entries("headlesscode", OLLAMA, OVERRIDE_MODEL)


def test_uwuchat_embedding_stays_cloud_under_ollama_override(
    _ollama_env,
) -> None:
    """EMBEDDING stays cloud even when text pipelines go ollama."""
    _reload_module("uwuchat")
    _assert_embedding_pinned("uwuchat")


def test_headlesscode_embedding_stays_cloud_under_ollama_override(
    _ollama_env,
) -> None:
    """EMBEDDING stays cloud even when text pipelines go ollama."""
    _reload_module("headlesscode")
    _assert_embedding_pinned("headlesscode")


def test_ollama_override_never_touches_local_provider() -> None:
    """No text pipeline can fall through to the framework 'local'."""
    os.environ["AIRUNNER_LLM_PROVIDER"] = OLLAMA
    os.environ["AIRUNNER_LLM_MODEL"] = OVERRIDE_MODEL
    try:
        _assert_text_entries("uwuchat", OLLAMA, OVERRIDE_MODEL)
        _assert_text_entries("headlesscode", OLLAMA, OVERRIDE_MODEL)
    finally:
        del os.environ["AIRUNNER_LLM_PROVIDER"]
        del os.environ["AIRUNNER_LLM_MODEL"]
    for project in PROJECTS:
        for key, entry in _configured_text_entries(project):
            if key.startswith("DIALOGUE/tier/"):
                continue
            assert entry["provider"] != LOCAL, (
                f"{project} {key} must never select local"
            )


def test_module_reimport_restores_defaults_after_override() -> None:
    """A fresh import with the env unset restores cloud defaults."""
    os.environ["AIRUNNER_LLM_PROVIDER"] = OLLAMA
    os.environ["AIRUNNER_LLM_MODEL"] = OVERRIDE_MODEL
    try:
        _assert_text_entries("uwuchat", OLLAMA, OVERRIDE_MODEL)
    finally:
        del os.environ["AIRUNNER_LLM_PROVIDER"]
        del os.environ["AIRUNNER_LLM_MODEL"]
    _assert_defaults_unchanged("uwuchat")


@pytest.mark.parametrize("project", PROJECTS)
def test_pipeline_module_imports_cleanly(project: str) -> None:
    """The project pipeline module imports without side effects."""
    module = _reload_module(project)
    assert "PIPELINE_CONFIG" in dir(module)
