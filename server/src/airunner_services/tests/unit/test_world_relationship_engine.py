"""Unit tests for world.relationship_engine warmth/trust tracking."""

from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import patch

from airunner_services.world.relationship_engine import (
    _clamp,
    _decay_factor,
    get_or_create_relationship,
    get_relationship_context,
    record_interaction,
)

_RELATIONSHIP_PATH = "airunner_services.database.models.relationship.Relationship"


class TestClamp:
    """Tests for _clamp."""

    def test_clamps_low(self) -> None:
        """Values below zero clamp to zero."""
        assert _clamp(-0.5) == 0.0

    def test_clamps_high(self) -> None:
        """Values above one clamp to one."""
        assert _clamp(1.5) == 1.0

    def test_passthrough(self) -> None:
        """Values in range pass through unchanged."""
        assert _clamp(0.4) == 0.4


class TestDecayFactor:
    """Tests for _decay_factor."""

    def test_none_is_zero(self) -> None:
        """A missing timestamp means no decay."""
        assert _decay_factor(None) == 0.0

    def test_elapsed_days(self) -> None:
        """Decay grows with elapsed days."""
        old = datetime.datetime.utcnow() - datetime.timedelta(days=10)
        assert 9.9 < _decay_factor(old) < 10.1

    def test_future_timestamp_zero(self) -> None:
        """A future timestamp never decays below zero."""
        future = datetime.datetime.utcnow() + datetime.timedelta(days=5)
        assert _decay_factor(future) == 0.0


class TestGetOrCreateRelationship:
    """Tests for get_or_create_relationship."""

    def test_creates_with_neutral_defaults(self) -> None:
        """A missing relationship is created with neutral values."""
        with patch(_RELATIONSHIP_PATH) as mock_model:
            mock_model.objects.query.return_value.filter.return_value.first.return_value = None
            created = SimpleNamespace(id=1)
            mock_model.objects.create.return_value = created
            result = get_or_create_relationship(7, "user", 3)
        assert result is created
        kwargs = mock_model.objects.create.call_args[1]
        assert kwargs["chatbot_id"] == 7
        assert kwargs["target_type"] == "user"
        assert kwargs["target_id"] == 3
        assert kwargs["warmth"] == 0.5
        assert kwargs["trust"] == 0.5

    def test_reuses_existing(self) -> None:
        """An existing relationship is returned."""
        existing = SimpleNamespace(id=1)
        with patch(_RELATIONSHIP_PATH) as mock_model:
            mock_model.objects.query.return_value.filter.return_value.first.return_value = existing
            result = get_or_create_relationship(7, "user", 3)
        assert result is existing
        mock_model.objects.create.assert_not_called()

    def test_failure_returns_none(self) -> None:
        """A failure degrades to None."""
        with patch(_RELATIONSHIP_PATH) as mock_model:
            mock_model.objects.query.return_value.filter.return_value.first.side_effect = RuntimeError(
                "boom"
            )
            assert get_or_create_relationship(7, "user", 3) is None


class TestRecordInteraction:
    """Tests for record_interaction."""

    def test_updates_warmth_and_trust(self) -> None:
        """Warmth and trust rise after an interaction."""
        rel = SimpleNamespace(
            id=1, warmth=0.5, trust=0.5, last_interaction_at=None, dynamic="friend"
        )
        with (
            patch(
                "airunner_services.world.relationship_engine"
                ".get_or_create_relationship",
                return_value=rel,
            ),
            patch(_RELATIONSHIP_PATH) as mock_model,
        ):
            record_interaction(7, "user", 3, emotional_weight=0.3)
        kwargs = mock_model.objects.update.call_args[1]
        assert kwargs["warmth"] > 0.5
        assert kwargs["trust"] > 0.5
        assert kwargs["last_interaction_at"] is not None

    def test_clamps_to_one(self) -> None:
        """Repeated boosts never exceed 1.0."""
        rel = SimpleNamespace(
            id=1, warmth=0.99, trust=0.99, last_interaction_at=None, dynamic="friend"
        )
        with (
            patch(
                "airunner_services.world.relationship_engine"
                ".get_or_create_relationship",
                return_value=rel,
            ),
            patch(_RELATIONSHIP_PATH) as mock_model,
        ):
            record_interaction(7, "user", 3, emotional_weight=1.0)
        kwargs = mock_model.objects.update.call_args[1]
        assert kwargs["warmth"] <= 1.0
        assert kwargs["trust"] <= 1.0

    def test_missing_relationship_noop(self) -> None:
        """A missing relationship makes the update a no-op."""
        with (
            patch(
                "airunner_services.world.relationship_engine"
                ".get_or_create_relationship",
                return_value=None,
            ),
            patch(_RELATIONSHIP_PATH) as mock_model,
        ):
            record_interaction(7, "user", 3)
            mock_model.objects.update.assert_not_called()


class TestGetRelationshipContext:
    """Tests for get_relationship_context."""

    def test_missing_relationship_none(self) -> None:
        """No relationship yields no context."""
        with patch(_RELATIONSHIP_PATH) as mock_model:
            mock_model.objects.query.return_value.filter.return_value.first.return_value = None
            assert get_relationship_context(7, "user", 3) is None

    def test_builds_summary(self) -> None:
        """Warmth and trust map to descriptive labels."""
        rel = SimpleNamespace(warmth=0.9, trust=0.7, dynamic="close friend")
        with patch(_RELATIONSHIP_PATH) as mock_model:
            mock_model.objects.query.return_value.filter.return_value.first.return_value = rel
            text = get_relationship_context(7, "user", 3)
        assert text is not None
        assert "close friend" in text
        assert "deeply fond of" in text
        assert "generally trusts" in text

    def test_failure_returns_none(self) -> None:
        """A failure degrades to None."""
        with patch(_RELATIONSHIP_PATH) as mock_model:
            mock_model.objects.query.return_value.filter.return_value.first.side_effect = RuntimeError(
                "boom"
            )
            assert get_relationship_context(7, "user", 3) is None
