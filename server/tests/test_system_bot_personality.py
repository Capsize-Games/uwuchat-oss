"""Tests for system-bot personality/core-rules text — verifies the
topic-change compliance instruction is a standalone, explicit CRITICAL
directive (separate from core_rules) that overrides the
"sharp/curious/pushes back" personality trait, and that the
prompt-builder places it before the agent-memory / episodic-summary
blocks rather than after them (those blocks narrate detailed, often
emotionally loaded past topics; reading the override only after them
defeats the point of stating it prominently)."""

from __future__ import annotations

from projects.uwuchat.server.seed import _SYSTEM_BOT_PERSONALITY
from projects.uwuchat.server.system_bot_prompt import (
    uwu_system_bot_core_rules,
    uwu_system_bot_topic_change_rule,
)


def test_personality_scopes_pushback_to_claims_only() -> None:
    """_SYSTEM_BOT_PERSONALITY must scope pushback to claims/reasoning,
    with no second mention of pushback in relation to new subjects."""
    assert "push back on claims and reasoning" in _SYSTEM_BOT_PERSONALITY, (
        "Scoped pushback wording must still be present"
    )
    assert (
        "push back when something doesn't make sense"
        not in _SYSTEM_BOT_PERSONALITY
    ), "Unscoped pushback phrase must not reappear"
    assert (
        "push back" not in _SYSTEM_BOT_PERSONALITY.split(
            "reasoning that don't hold up"
        )[1]
    ), "No second mention of pushback (e.g. re: topic changes) should exist"


def test_core_rules_pushback_carveout_is_narrow() -> None:
    """The pushback carve-out in core rules must stay scoped to tool
    results / the system date, with no topic-change clause bolted on."""
    rules = uwu_system_bot_core_rules()
    assert (
        "applies to the user's claims and the conversation's logic"
        in rules
    )
    assert "does NOT mean doubting your own already-verified tool" in rules
    assert "does NOT apply to the user changing the subject" not in rules, (
        "Carve-out must not name topic-change as a forbidden pushback case"
    )


def test_core_rules_no_longer_contains_topic_change_directive() -> None:
    """The CRITICAL directive must live in its own function, not be
    bundled inside core_rules (which is assembled after the memory
    blocks — too late for a primacy effect to help)."""
    rules = uwu_system_bot_core_rules()
    assert "CRITICAL — TOPIC CHANGES ARE NORMAL" not in rules


def test_topic_change_rule_is_prominent_and_explicit() -> None:
    """The standalone topic-change directive names and overrides the
    specific forbidden behaviors we've observed the model produce."""
    rule = uwu_system_bot_topic_change_rule()
    assert "CRITICAL — TOPIC CHANGES ARE NORMAL" in rule
    assert "NEVER ask if they are testing you" in rule
    assert "NEVER ask why they changed the" in rule
    assert "overrides any general instinct elsewhere in this prompt" in rule
