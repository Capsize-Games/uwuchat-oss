"""Async weather plumbing tests for prompt-builder injection.

Covers ``fetch_weather_async`` (the non-blocking wrapper), the two
prompt-builder weather parts that now ``await`` it, and a structural
guard that the whole per-turn context chain stays async so a future
change cannot silently reintroduce a blocking ``fetch_weather`` call
inside prompt assembly.
"""

from __future__ import annotations

import inspect

from airunner_services.services.weather_service import (
    fetch_weather_async,
)


def _weather_dict() -> dict:
    """Return a canned Open-Meteo-shaped result dict."""
    return {
        "temperature": 12, "temperature_unit": "°F",
        "wind_speed": 5, "wind_speed_unit": "mph",
        "wind_gusts": 8, "snowfall": 0, "rain": 0,
        "precipitation": 0, "precipitation_unit": "inch",
        "forecast_text": "",
    }


def test_fetch_weather_async_is_coroutine() -> None:
    """The wrapper is a coroutine function (not a sync call)."""
    assert inspect.iscoroutinefunction(fetch_weather_async)


async def test_fetch_weather_async_delegates_to_sync_fetch() -> None:
    """Async wrapper returns the sync fetch_weather result unchanged."""
    from unittest.mock import patch

    expected = _weather_dict()
    with patch(
        "airunner_services.services.weather_service.fetch_weather",
        return_value=expected,
    ) as mock_fetch:
        result = await fetch_weather_async(52.52, 13.405, "metric")

    assert result == expected
    mock_fetch.assert_called_once_with(52.52, 13.405, "metric")


async def test_fetch_weather_async_returns_none_on_failure() -> None:
    """Async wrapper propagates fetch_weather's None failure result."""
    from unittest.mock import patch

    with patch(
        "airunner_services.services.weather_service.fetch_weather",
        return_value=None,
    ) as mock_fetch:
        result = await fetch_weather_async(1.0, 2.0)

    assert result is None
    mock_fetch.assert_called_once_with(1.0, 2.0, "imperial")


async def test_bot_weather_part_awaits_async_wrapper() -> None:
    """bot_weather_part awaits fetch_weather_async, not the sync call."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from airunner_services.contract_enums import LLMActionType
    from airunner_services.llm.managers.prompt_builder.per_turn_extras import (
        bot_weather_part,
    )

    chatbot = MagicMock()
    chatbot.is_system_bot = True
    chatbot.use_weather_prompt = True
    chatbot.location = {
        "latitude": 52.52, "longitude": 13.405, "city": "",
    }
    user = MagicMock()
    user.unit_system = "imperial"
    owner = MagicMock()
    owner.chatbot = chatbot
    owner.user = user

    with patch(
        "airunner_services.downloads.policy.is_openmeteo_allowed",
        return_value=True,
    ), patch(
        "airunner_services.services.weather_service.fetch_weather_async",
        new=AsyncMock(return_value=_weather_dict()),
    ) as mock_fetch:
        result = await bot_weather_part(owner, LLMActionType.CHAT)

    assert result is not None
    assert "Temperature: 12°F" in result
    assert "Wind: 5 mph (gusts 8 mph)" in result
    mock_fetch.assert_awaited_once_with(52.52, 13.405, "imperial")


async def test_weather_part_awaits_async_wrapper() -> None:
    """_weather_part awaits fetch_weather_async, not the sync call."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from airunner_services.contract_enums import LLMActionType
    from airunner_services.llm.managers.prompt_builder.per_turn_context import (
        _weather_part,
    )

    chatbot = MagicMock()
    chatbot.use_weather_prompt = True
    user = MagicMock()
    user.latitude = 52.52
    user.longitude = 13.405
    user.unit_system = "metric"
    owner = MagicMock()
    owner.chatbot = chatbot
    owner.user = user

    with patch(
        "airunner_services.downloads.policy.is_openmeteo_allowed",
        return_value=True,
    ), patch(
        "airunner_services.services.weather_service.fetch_weather_async",
        new=AsyncMock(return_value=_weather_dict()),
    ) as mock_fetch:
        result = await _weather_part(owner, LLMActionType.CHAT)

    assert result is not None
    assert "What I perceive in your world right now" in result
    mock_fetch.assert_awaited_once_with(52.52, 13.405, "metric")


def test_per_turn_context_chain_is_async() -> None:
    """Every function in the per-turn context chain is a coroutine.

    Regression guard: if any link in the chain reverts to a sync
    ``def``, the ``await`` at the next level up fails loudly at import
    / call time.  This test names each link so the failure message
    points at the exact function that regressed.
    """
    from airunner_services.llm.managers.mixins import (
        generation_execution_support,
        generation_workflow_support,
        request_handling_mixin,
    )
    from airunner_services.llm.managers.mixins.generation_mixin import (
        GenerationMixin,
    )
    from airunner_services.llm.managers.prompt_builder import (
        per_turn_context,
        per_turn_extras,
    )

    coroutines = [
        per_turn_context.collect_per_turn_context,
        per_turn_context._weather_part,
        per_turn_extras.bot_weather_part,
        generation_workflow_support._store_per_turn_context,
        generation_workflow_support.setup_generation_workflow,
        generation_execution_support.do_generate,
        GenerationMixin._do_generate,
        request_handling_mixin.RequestHandlingCoreMixin.handle_request,
        fetch_weather_async,
    ]
    non_async = [
        fn.__name__ for fn in coroutines
        if not inspect.iscoroutinefunction(fn)
    ]
    assert not non_async, f"Expected coroutine functions: {non_async}"
