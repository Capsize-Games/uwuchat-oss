"""Unit tests for world.growth_engine identity evolution."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from airunner_services.world.growth_engine import (
    EMOTIONAL_WEIGHT_THRESHOLD,
    GrowthEngine,
    _apply_growth,
    _build_prompt,
    _parse_growth,
    _should_grow,
)


class TestShouldGrow:
    """Tests for _should_grow."""

    def test_high_weight_grows(self) -> None:
        """A weight at the threshold triggers growth."""
        session = SimpleNamespace(emotional_weight=EMOTIONAL_WEIGHT_THRESHOLD)
        assert _should_grow(session) is True

    def test_low_weight_no_grow(self) -> None:
        """A weight below the threshold does not trigger growth."""
        session = SimpleNamespace(emotional_weight=0.2)
        assert _should_grow(session) is False

    def test_missing_weight_no_grow(self) -> None:
        """A missing weight never triggers growth."""
        session = SimpleNamespace(emotional_weight=None)
        assert _should_grow(session) is False


class TestParseGrowth:
    """Tests for _parse_growth."""

    def test_extracts_json(self) -> None:
        """A JSON object is extracted from the response."""
        raw = '{"new_formative_event": "Met a mentor"}'
        assert _parse_growth(raw) == {"new_formative_event": "Met a mentor"}

    def test_invalid_returns_none(self) -> None:
        """Unparseable output yields None."""
        assert _parse_growth("nope") is None


class TestApplyGrowth:
    """Tests for _apply_growth."""

    def test_appends_formative_event(self) -> None:
        """A new formative event is appended to the background."""
        bot = MagicMock()
        bot.identity_core = {
            "archetype": "wanderer",
            "background": {"formative_events": ["old event"]},
        }
        core = _apply_growth(
            bot,
            {
                "new_formative_event": "new event",
                "revised_worldview": None,
                "new_interest": None,
            },
        )
        assert core["background"]["formative_events"] == ["old event", "new event"]

    def test_skips_duplicate_event(self) -> None:
        """A duplicate event is not appended twice."""
        bot = MagicMock()
        bot.identity_core = {
            "background": {"formative_events": ["event"]},
        }
        core = _apply_growth(
            bot,
            {
                "new_formative_event": "event",
                "revised_worldview": None,
                "new_interest": None,
            },
        )
        assert core["background"]["formative_events"] == ["event"]

    def test_caps_events_at_eight(self) -> None:
        """Formative events are capped at eight entries."""
        bot = MagicMock()
        bot.identity_core = {
            "background": {"formative_events": [f"e{i}" for i in range(8)]},
        }
        core = _apply_growth(
            bot,
            {
                "new_formative_event": "e9",
                "revised_worldview": None,
                "new_interest": None,
            },
        )
        assert len(core["background"]["formative_events"]) == 8
        assert core["background"]["formative_events"][-1] == "e9"

    def test_revises_worldview(self) -> None:
        """A revised worldview replaces the background worldview."""
        bot = MagicMock()
        bot.identity_core = {"background": {"worldview": "old"}}
        core = _apply_growth(
            bot,
            {
                "new_formative_event": None,
                "revised_worldview": "new worldview",
                "new_interest": None,
            },
        )
        assert core["background"]["worldview"] == "new worldview"

    def test_adds_new_interest_to_values(self) -> None:
        """A new interest is added to cultural values."""
        bot = MagicMock()
        bot.identity_core = {
            "beliefs": {"cultural_values": ["curiosity"]},
        }
        core = _apply_growth(
            bot,
            {
                "new_formative_event": None,
                "revised_worldview": None,
                "new_interest": "photography",
            },
        )
        assert core["beliefs"]["cultural_values"] == ["curiosity", "photography"]


class TestBuildPrompt:
    """Tests for _build_prompt."""

    def test_embeds_session_data(self) -> None:
        """The prompt embeds archetype, events, and session summary."""
        bot = MagicMock()
        bot.identity_core = {
            "archetype": "wanderer",
            "background": {"formative_events": ["a", "b"]},
        }
        bot.botname = "Kuma"
        session = SimpleNamespace(
            episodic_summary="a pivotal session", emotional_weight=0.8
        )
        prompt = _build_prompt(bot, session)
        assert "wanderer" in prompt
        assert "a pivotal session" in prompt
        assert "0.8" in prompt


class TestGrowthEngine:
    """Tests for GrowthEngine orchestration."""

    def test_maybe_evolve_applies_growth(self) -> None:
        """A qualifying session triggers a growth step."""
        session = SimpleNamespace(
            emotional_weight=0.9,
            episodic_summary="heavy session",
        )
        bot = MagicMock()
        bot.id = 1
        bot.identity_core = {
            "archetype": "wanderer",
            "background": {"formative_events": []},
        }
        engine = GrowthEngine(MagicMock())
        mock_query = MagicMock()
        mock_query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            session
        ]
        with (
            patch(
                "airunner_services.database.models.chat_session.ChatSession"
            ) as mock_model,
            patch.object(engine, "_evolve") as mock_evolve,
        ):
            mock_model.objects.query.return_value = mock_query
            engine.maybe_evolve(bot)
            mock_evolve.assert_called_once_with(bot, session)

    def test_maybe_evolve_no_qualifying_sessions(self) -> None:
        """Sessions below the threshold do not trigger growth."""
        session = SimpleNamespace(emotional_weight=0.1)
        bot = MagicMock()
        bot.id = 1
        engine = GrowthEngine(MagicMock())
        mock_query = MagicMock()
        mock_query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            session
        ]
        with (
            patch(
                "airunner_services.database.models.chat_session.ChatSession"
            ) as mock_model,
            patch.object(engine, "_evolve") as mock_evolve,
        ):
            mock_model.objects.query.return_value = mock_query
            engine.maybe_evolve(bot)
            mock_evolve.assert_not_called()

    def test_evolve_persists_updated_core(self) -> None:
        """A parsed growth update is persisted to the chatbot."""
        bot = MagicMock()
        bot.id = 1
        bot.identity_core = {
            "archetype": "wanderer",
            "background": {"formative_events": []},
        }
        session = SimpleNamespace(emotional_weight=0.9, episodic_summary="s")
        engine = GrowthEngine(MagicMock())
        raw = (
            '{"new_formative_event": "Learned to trust", '
            '"revised_worldview": null, "new_interest": null}'
        )
        with (
            patch.object(engine, "_call_llm", return_value=raw),
            patch("airunner_services.database.models.chatbot.Chatbot") as mock_model,
        ):
            engine._evolve(bot, session)
        kwargs = mock_model.objects.update.call_args[1]
        assert kwargs["identity_core"]["background"]["formative_events"] == [
            "Learned to trust"
        ]

    def test_evolve_empty_llm_noop(self) -> None:
        """An empty LLM response leaves the chatbot untouched."""
        bot = MagicMock()
        bot.id = 1
        bot.identity_core = {"background": {"formative_events": []}}
        session = SimpleNamespace(emotional_weight=0.9, episodic_summary="s")
        engine = GrowthEngine(MagicMock())
        with (
            patch.object(engine, "_call_llm", return_value=""),
            patch("airunner_services.database.models.chatbot.Chatbot") as mock_model,
        ):
            engine._evolve(bot, session)
            mock_model.objects.update.assert_not_called()
