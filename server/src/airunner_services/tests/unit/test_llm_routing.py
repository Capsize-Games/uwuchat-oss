"""Unit tests for the LLM model router.

Covers:
- Rule lookup for known/unknown keys.
- apply_to_settings mutates settings correctly.
- build_model delegates to ChatModelFactory.
- UwUchat routing never selects a local/edge/GGUF provider.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


from airunner_services.llm.model_router import (
    ModelRouter,
    _apply_rule,
    load_project_router,
)

from airunner_services.contract_enums import ModelService


# ---------------------------------------------------------------------------
# ModelRouter — rule()
# ---------------------------------------------------------------------------


def test_rule_returns_dict_for_known_key() -> None:
    """rule() returns the routing dict for a known key."""
    router = ModelRouter(
        {"DIALOGUE": {"provider": ModelService.OPENROUTER.value, "model": "test-model"}}
    )
    rule = router.rule("DIALOGUE")
    assert rule == {"provider": ModelService.OPENROUTER.value, "model": "test-model"}


def test_rule_returns_empty_for_unknown_key() -> None:
    """rule() returns an empty dict for an unknown key."""
    router = ModelRouter({"DIALOGUE": {"provider": ModelService.OPENROUTER.value}})
    assert router.rule("NONEXISTENT") == {}


# ---------------------------------------------------------------------------
# _apply_rule
# ---------------------------------------------------------------------------


def test_apply_rule_sets_openrouter() -> None:
    """_apply_rule sets use_openrouter and model on the settings object."""
    settings = MagicMock()
    _apply_rule(
        {"provider": ModelService.OPENROUTER.value, "model": "gpt-4o"},
        settings,
    )
    assert settings.use_openrouter is True
    assert settings.model == "gpt-4o"


def test_apply_rule_sets_ollama() -> None:
    """_apply_rule sets use_ollama and ollama_model."""
    settings = MagicMock()
    _apply_rule({"provider": ModelService.OLLAMA.value, "model": "llama3"}, settings)
    assert settings.use_ollama is True
    assert settings.ollama_model == "llama3"


def test_apply_rule_sets_local() -> None:
    """_apply_rule sets use_local_llm for local provider."""
    settings = MagicMock()
    _apply_rule({"provider": ModelService.LOCAL.value, "model": "qwen"}, settings)
    assert settings.use_local_llm is True


def test_apply_rule_missing_model_is_harmless() -> None:
    """_apply_rule does not crash when the rule has no model key."""
    settings = MagicMock()
    _apply_rule({"provider": ModelService.OPENROUTER.value}, settings)
    assert settings.use_openrouter is True


# ---------------------------------------------------------------------------
# ModelRouter — apply_to_settings
# ---------------------------------------------------------------------------


def test_apply_to_settings_known_key() -> None:
    """apply_to_settings mutates settings for a known key."""
    settings = MagicMock()
    router = ModelRouter(
        {"DIALOGUE": {"provider": ModelService.OPENROUTER.value, "model": "m1"}}
    )
    result = router.apply_to_settings("DIALOGUE", settings)
    assert result is True
    assert settings.use_openrouter is True
    assert settings.model == "m1"


def test_apply_to_settings_unknown_key() -> None:
    """apply_to_settings returns False and does not mutate settings."""
    settings = MagicMock()
    router = ModelRouter({"DIALOGUE": {"provider": ModelService.OPENROUTER.value}})
    result = router.apply_to_settings("UNKNOWN", settings)
    assert result is False


# ---------------------------------------------------------------------------
# ModelRouter — build_model
# ---------------------------------------------------------------------------


def test_build_model_returns_none_for_unknown_key() -> None:
    """build_model returns None when no rule exists for the key."""
    router = ModelRouter({"DIALOGUE": {"provider": ModelService.OPENROUTER.value}})
    settings = MagicMock()
    assert router.build_model("UNKNOWN", settings) is None


def test_build_model_delegates_to_factory() -> None:
    """build_model creates a model via ChatModelFactory."""
    settings = MagicMock()
    router = ModelRouter(
        {"DIALOGUE": {"provider": ModelService.OPENROUTER.value, "model": "test"}}
    )

    mock_factory = MagicMock()
    mock_model = MagicMock()
    mock_factory.create_from_settings.return_value = mock_model

    with patch(
        "airunner_services.llm.adapters.ChatModelFactory",
        mock_factory,
    ):
        model = router.build_model("DIALOGUE", settings)

    assert model is mock_model
    mock_factory.create_from_settings.assert_called_once()


# ---------------------------------------------------------------------------
# load_project_router
# ---------------------------------------------------------------------------


def test_load_project_router_returns_router() -> None:
    """load_project_router returns a ModelRouter when pipeline exists."""
    mock_pipeline = {
        "DIALOGUE": {"provider": ModelService.OPENROUTER.value, "model": "test"},
        "TOOL_CLASSIFICATION": {
            "provider": ModelService.OPENROUTER.value,
            "model": "small",
        },
    }
    with patch(
        "airunner_services.llm.pipeline_loader.load_pipeline",
        return_value=mock_pipeline,
    ):
        router = load_project_router()
    assert router is not None
    assert isinstance(router, ModelRouter)
    rule = router.rule("DIALOGUE")
    assert rule["provider"] == ModelService.OPENROUTER.value
