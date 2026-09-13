"""Unit tests for world.curiosity_engine topic tracking and search."""

from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import patch

from airunner_services.world.curiosity_engine import (
    CURIOSITY_SEARCH_THRESHOLD,
    CuriosityEngine,
    _curiosity_data,
    _hours_since_searched,
    _persist_curiosity,
    _record_search,
    _topic_score,
    bump_topics,
)


class TestCuriosityData:
    """Tests for _curiosity_data."""

    def test_returns_copy_of_data(self) -> None:
        """Existing curiosity data is returned as a dict."""
        bot = SimpleNamespace(curiosity_data={"topics": {"a": {}}})
        assert _curiosity_data(bot) == {"topics": {"a": {}}}

    def test_missing_defaults_to_empty(self) -> None:
        """Missing curiosity data defaults to an empty dict."""
        bot = SimpleNamespace(curiosity_data=None)
        assert _curiosity_data(bot) == {}


class TestTopicScore:
    """Tests for _topic_score."""

    def test_existing_score(self) -> None:
        """The stored score is returned."""
        curiosity = {"topics": {"music": {"score": 4}}}
        assert _topic_score(curiosity, "music") == 4

    def test_missing_score_zero(self) -> None:
        """A missing topic scores zero."""
        assert _topic_score({}, "music") == 0


class TestHoursSinceSearched:
    """Tests for _hours_since_searched."""

    def test_never_searched_infinite(self) -> None:
        """A topic that was never searched reads as infinite."""
        assert _hours_since_searched({}, "music") == float("inf")

    def test_invalid_timestamp_infinite(self) -> None:
        """A malformed timestamp reads as infinite."""
        curiosity = {"topics": {"music": {"last_searched_at": "garbage"}}}
        assert _hours_since_searched(curiosity, "music") == float("inf")

    def test_computes_hours(self) -> None:
        """Elapsed hours since the last search are returned."""
        ts = datetime.datetime.utcnow() - datetime.timedelta(hours=5)
        curiosity = {"topics": {"music": {"last_searched_at": ts.isoformat()}}}
        assert 4.9 < _hours_since_searched(curiosity, "music") < 5.1


class TestRecordSearch:
    """Tests for _record_search."""

    def test_stamps_timestamp(self) -> None:
        """A search timestamp is recorded for the topic."""
        updated = _record_search({}, "music")
        entry = updated["topics"]["music"]
        assert entry["last_searched_at"] is not None


class TestBumpTopics:
    """Tests for bump_topics."""

    def test_increments_scores(self) -> None:
        """Each topic's score increments by one."""
        updated = bump_topics(7, ["music", "art"], {"topics": {}})
        assert updated["topics"]["music"]["score"] == 1
        assert updated["topics"]["art"]["score"] == 1

    def test_accumulates_existing_score(self) -> None:
        """An existing score keeps accumulating."""
        curiosity = {"topics": {"music": {"score": 2}}}
        updated = bump_topics(7, ["music"], curiosity)
        assert updated["topics"]["music"]["score"] == 3


class TestPersistCuriosity:
    """Tests for _persist_curiosity."""

    def test_persists_via_chatbot_model(self) -> None:
        """The updated dict is saved to the chatbot."""
        data = {"topics": {"music": {"score": 1}}}
        with patch("airunner_services.database.models.chatbot.Chatbot") as mock_model:
            _persist_curiosity(7, data)
            mock_model.objects.update.assert_called_once_with(7, curiosity_data=data)

    def test_failure_is_swallowed(self) -> None:
        """A DB failure does not raise."""
        with patch("airunner_services.database.models.chatbot.Chatbot") as mock_model:
            mock_model.objects.update.side_effect = RuntimeError("boom")
            _persist_curiosity(7, {})


class TestCuriosityEngine:
    """Tests for CuriosityEngine.tick."""

    def test_no_preoccupations_returns_none(self) -> None:
        """A chatbot without preoccupations triggers nothing."""
        bot = SimpleNamespace(
            id=7,
            curiosity_data=None,
            inner_state={"preoccupations": []},
        )
        engine = CuriosityEngine()
        with patch(
            "airunner_services.world.curiosity_engine._persist_curiosity"
        ) as mock_persist:
            assert engine.tick(bot) is None
            mock_persist.assert_not_called()

    def test_search_triggers_at_threshold(self) -> None:
        """A scored topic past cooldown triggers a search."""
        ts = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
        bot = SimpleNamespace(
            id=7,
            curiosity_data={
                "topics": {
                    "music": {
                        "score": CURIOSITY_SEARCH_THRESHOLD,
                        "last_searched_at": ts.isoformat(),
                    }
                }
            },
            inner_state={"preoccupations": ["music"]},
        )
        engine = CuriosityEngine()
        results = [
            {"title": "Music headline", "body": "body"},
            {"title": "Another", "body": "x"},
        ]
        with (
            patch.object(engine, "_search", return_value=results) as mock_search,
            patch(
                "airunner_services.world.curiosity_engine._persist_curiosity"
            ) as mock_persist,
        ):
            snippets = engine.tick(bot)
        assert snippets == ["Music headline", "Another"]
        mock_search.assert_called_once_with("music")
        mock_persist.assert_called_once()

    def test_search_skipped_below_threshold(self) -> None:
        """A topic below the threshold does not search."""
        bot = SimpleNamespace(
            id=7,
            curiosity_data={"topics": {"music": {"score": 1}}},
            inner_state={"preoccupations": ["music"]},
        )
        engine = CuriosityEngine()
        with (
            patch.object(engine, "_search") as mock_search,
            patch(
                "airunner_services.world.curiosity_engine._persist_curiosity"
            ) as mock_persist,
        ):
            assert engine.tick(bot) is None
            mock_search.assert_not_called()
            mock_persist.assert_called_once()

    def test_no_results_returns_none(self) -> None:
        """A search with no results yields no snippets."""
        ts = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
        bot = SimpleNamespace(
            id=7,
            curiosity_data={
                "topics": {
                    "music": {
                        "score": CURIOSITY_SEARCH_THRESHOLD,
                        "last_searched_at": ts.isoformat(),
                    }
                }
            },
            inner_state={"preoccupations": ["music"]},
        )
        engine = CuriosityEngine()
        with (
            patch.object(engine, "_search", return_value=[]),
            patch("airunner_services.world.curiosity_engine._persist_curiosity"),
        ):
            assert engine.tick(bot) is None

    def test_search_failure_returns_empty(self) -> None:
        """A search failure degrades to an empty list."""
        engine = CuriosityEngine()
        with patch(
            "extensions.fastsearch.server.provider.FastSearchProvider.search",
            side_effect=RuntimeError("boom"),
        ):
            assert engine._search("music") == []
