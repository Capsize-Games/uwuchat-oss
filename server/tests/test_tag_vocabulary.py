"""Tests for tag_vocabulary — Part 6 controlled tag vocabulary."""
from __future__ import annotations

from airunner_services.tag_vocabulary import normalize_tag, normalize_tags


def test_normalize_exact_match() -> None:
    assert normalize_tag("Identity") == "Identity"
    assert normalize_tag("Health") == "Health"
    assert normalize_tag("Work") == "Work"


def test_normalize_case_insensitive() -> None:
    assert normalize_tag("identity") == "Identity"
    assert normalize_tag("HEALTH") == "Health"
    assert normalize_tag("WoRk") == "Work"


def test_normalize_unknown_returns_none() -> None:
    assert normalize_tag("Career") is None
    assert normalize_tag("Job") is None
    assert normalize_tag("random tag") is None


def test_normalize_empty_returns_none() -> None:
    assert normalize_tag("") is None
    assert normalize_tag("  ") is None


def test_normalize_tags_string() -> None:
    result = normalize_tags("Identity, Health, Career")
    assert result == ["Identity", "Health"]


def test_normalize_tags_dedup() -> None:
    result = normalize_tags("identity, Identity, IDENTITY")
    assert result == ["Identity"]


def test_normalize_tags_list() -> None:
    result = normalize_tags(["Work", "job", "Goals"])
    assert result == ["Work", "Goals"]


def test_normalize_tags_none() -> None:
    assert normalize_tags(None) == []


def test_all_vocabulary_present() -> None:
    """All vocabulary entries normalize to themselves."""
    from airunner_services.tag_vocabulary import _VOCABULARY
    for tag in _VOCABULARY:
        assert normalize_tag(tag) == tag
