"""Unit tests for UwUchat prompt_rules — Plan 3 and Plan 4 fixes.

Tests that the correction-tone rule and fabricated-personal-state rule
are present in BANNED_PATTERNS_BLOCK.
"""

from __future__ import annotations

from projects.uwuchat.server.prompt_rules import BANNED_PATTERNS_BLOCK


def test_banned_patterns_includes_correction_tone_rule() -> None:
    """BANNED_PATTERNS_BLOCK contains the proportional-correction rule."""
    assert "acknowledge the correction" in BANNED_PATTERNS_BLOCK
    assert "Never deliver a multi-sentence apology" in BANNED_PATTERNS_BLOCK
    assert "never say 'I apologize'" in BANNED_PATTERNS_BLOCK
    assert (
        "One sentence acknowledging the correction is enough"
        in BANNED_PATTERNS_BLOCK
    )


def test_banned_patterns_includes_personal_state_rule() -> None:
    """BANNED_PATTERNS_BLOCK bans fabricating personal-state callbacks."""
    assert "do not create one to warm up the conversation" in (
        BANNED_PATTERNS_BLOCK
    )
    assert (
        "A plain greeting ('good morning', 'hey') does not invite"
        " a personalized callback" in BANNED_PATTERNS_BLOCK
    )
    assert "recent physical state" in BANNED_PATTERNS_BLOCK
    assert (
        "filling in specifics about their private experience that no"
        " one provided" in BANNED_PATTERNS_BLOCK
    )
