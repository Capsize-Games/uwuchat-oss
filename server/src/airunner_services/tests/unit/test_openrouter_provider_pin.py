"""Regression test for OpenRouter provider pinning.

Without an explicit provider pin, OpenRouter's auto-routing can send
consecutive requests in the same conversation to different backend
instances. Anthropic prompt caching is scoped per-instance, so a cache
written on one instance is invisible to a read on another -- silently
defeating caching even with a byte-identical prompt prefix. See
plans/ (round 6 of the tool-cost investigation) for the full trace.
"""
from airunner_services.cloud.llm.model_builders import (
    _provider_order_for_model,
    create_openrouter_model,
)

from airunner_services.conf.model_settings import (
    CLAUDE_HAIKU_MODEL,
    DEEPSEEK_V4_FLASH_MODEL,
    GOOGLE_GEMINI_FLASH_MODEL,
)


class TestOpenRouterProviderPin:
    def test_pins_to_google_vertex(self) -> None:
        model = create_openrouter_model(
            api_key="dummy",
            model_name=CLAUDE_HAIKU_MODEL,
        )
        assert model.extra_body == {
            "provider": {
                "order": ["google-vertex"],
                "allow_fallbacks": False,
            },
        }

    def test_pin_applies_regardless_of_model_name(self) -> None:
        model = create_openrouter_model(
            api_key="dummy",
            model_name=GOOGLE_GEMINI_FLASH_MODEL,
        )
        assert model.extra_body["provider"]["order"] == ["google-vertex"]
        assert model.extra_body["provider"]["allow_fallbacks"] is False

    def test_deepseek_pins_to_deepseek(self) -> None:
        assert _provider_order_for_model(DEEPSEEK_V4_FLASH_MODEL) == [
            "deepseek"
        ]
