"""Unit tests for the env-configurable Ollama base URL.

Work item W2 of ``plans/lan-shared-edge-inference.md``: the framework's
``ollama_base_url`` dataclass default must honor the
``AIRUNNER_OLLAMA_BASE_URL`` environment variable so each LAN stack can
point its chat pipelines at a shared local inference daemon.

The value flows through ``LazySettings`` (``airunner_services.conf``),
which caches its store after first resolution, and
``airunner_services.settings`` snapshots it at import time.  The tests
therefore set the env var, reset the lazy singleton, and re-import the
snapshotting modules — restoring both afterwards so the rest of the
suite is unaffected.
"""

from __future__ import annotations

import importlib

import pytest

DEFAULT_URL = "http://localhost:11434"
OVERRIDE_URL = "http://192.168.1.200:11434"


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unset the env var before every test so the default is clean."""
    monkeypatch.delenv("AIRUNNER_OLLAMA_BASE_URL", raising=False)


def _reload_settings_chain():
    """Reset LazySettings and re-import the snapshotting modules.

    Returns ``LLMSettings`` so callers can construct an instance.
    """
    import airunner_services.settings as settings_module
    from airunner_services import conf
    from airunner_services.llm import llm_settings

    conf.settings._resolved = False
    conf.settings._store = {}
    importlib.reload(settings_module)
    importlib.reload(llm_settings)
    return llm_settings.LLMSettings


def _restore_settings_chain() -> None:
    """Re-resolve LazySettings from the (now-restored) environment."""
    import airunner_services.settings as settings_module
    from airunner_services import conf
    from airunner_services.llm import llm_settings

    conf.settings._resolved = False
    conf.settings._store = {}
    importlib.reload(settings_module)
    importlib.reload(llm_settings)


def _ollama_base_url_with_env(env_value: str | None) -> str:
    """Return ``LLMSettings().ollama_base_url`` with env_value set."""
    import os

    old = os.environ.pop("AIRUNNER_OLLAMA_BASE_URL", None)
    if env_value is not None:
        os.environ["AIRUNNER_OLLAMA_BASE_URL"] = env_value
    try:
        llm_settings_cls = _reload_settings_chain()
        return llm_settings_cls().ollama_base_url
    finally:
        if old is None:
            os.environ.pop("AIRUNNER_OLLAMA_BASE_URL", None)
        else:
            os.environ["AIRUNNER_OLLAMA_BASE_URL"] = old
        _restore_settings_chain()


def test_defaults_to_localhost_when_env_unset() -> None:
    """With no env var, the default is the framework's localhost URL."""
    assert _ollama_base_url_with_env(None) == DEFAULT_URL


def test_honors_env_var() -> None:
    """``AIRUNNER_OLLAMA_BASE_URL`` overrides the dataclass default."""
    assert _ollama_base_url_with_env(OVERRIDE_URL) == OVERRIDE_URL
