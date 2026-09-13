"""Tests for the sensitive-category fact filter.

Covers: filtering inferred facts matching each GDPR Art. 9 category,
not filtering user_stated facts on the same topics, and not filtering
ordinary non-sensitive inferred facts.
"""

from __future__ import annotations

from airunner_services.knowledge_filters import filter_inferred_fact


class TestFilterInferredFact:
    """filter_inferred_fact blocks sensitive inferred facts."""

    def test_religion_inferred_is_blocked(self) -> None:
        """An inferred fact mentioning religion is blocked."""
        blocked, category = filter_inferred_fact(
            "The user is a practicing Catholic", "inferred",
        )
        assert blocked is True
        assert category == "religion"

    def test_politics_inferred_is_blocked(self) -> None:
        """An inferred fact mentioning political affiliation is blocked."""
        blocked, _ = filter_inferred_fact(
            "The user is a registered Democrat", "inferred",
        )
        assert blocked is True

    def test_health_inferred_is_blocked(self) -> None:
        """An inferred fact mentioning a health condition is blocked."""
        blocked, _ = filter_inferred_fact(
            "The user was diagnosed with diabetes last year", "inferred",
        )
        assert blocked is True

    def test_orientation_inferred_is_blocked(self) -> None:
        """An inferred fact mentioning sexual orientation is blocked."""
        blocked, _ = filter_inferred_fact(
            "They mentioned their husband — they are gay", "inferred",
        )
        assert blocked is True

    def test_race_inferred_is_blocked(self) -> None:
        """An inferred fact mentioning race or ethnicity is blocked."""
        blocked, _ = filter_inferred_fact(
            "The user identifies as African American", "inferred",
        )
        assert blocked is True

    def test_union_inferred_is_blocked(self) -> None:
        """An inferred fact mentioning union membership is blocked."""
        blocked, _ = filter_inferred_fact(
            "The user is a trade union member", "inferred",
        )
        assert blocked is True

    def test_biometric_inferred_is_blocked(self) -> None:
        """An inferred fact mentioning genetic/biometric data is blocked."""
        blocked, _ = filter_inferred_fact(
            "The user has a genetic predisposition for celiac disease",
            "inferred",
        )
        assert blocked is True

    def test_conversation_recall_is_filtered(self) -> None:
        """conversation_recall facts are also filtered."""
        blocked, _ = filter_inferred_fact(
            "The user is Muslim", "conversation_recall",
        )
        assert blocked is True

    # ── user_stated facts are NOT blocked ─────────────────────────

    def test_user_stated_religion_is_allowed(self) -> None:
        """A user_stated fact about religion is NOT blocked."""
        blocked, _ = filter_inferred_fact(
            "The user said they are Catholic", "user_stated",
        )
        assert blocked is False

    def test_user_stated_health_is_allowed(self) -> None:
        """A user_stated fact about health is NOT blocked."""
        blocked, _ = filter_inferred_fact(
            "The user told me they have diabetes", "user_stated",
        )
        assert blocked is False

    # ── Non-sensitive inferred facts are NOT blocked ──────────────

    def test_non_sensitive_inferred_is_allowed(self) -> None:
        """An ordinary inferred fact is not blocked."""
        blocked, _ = filter_inferred_fact(
            "The user works as a software engineer", "inferred",
        )
        assert blocked is False

    def test_web_search_source_is_not_filtered(self) -> None:
        """web_search facts are not filtered (they're about the world)."""
        blocked, _ = filter_inferred_fact(
            "Search result: Catholic population in Brazil", "web_search",
        )
        assert blocked is False

    def test_unknown_source_type_is_allowed(self) -> None:
        """Unknown source types are treated as not inferred."""
        blocked, _ = filter_inferred_fact(
            "Some fact with unknown source", "unknown",
        )
        assert blocked is False
