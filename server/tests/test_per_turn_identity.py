"""Tests for per_turn_identity — user identity block assembly.

Validates that user_identity_part correctly composes name and gender
lines from owner.user, and that two different user objects produce two
different identity blocks (regression test for the
User.objects.query().first() bug that was in the old user_belief_part).
"""

from __future__ import annotations

from unittest.mock import MagicMock

from airunner_services.contract_enums import LLMActionType
from airunner_services.llm.managers.prompt_builder.per_turn_identity import (
    user_identity_part,
)


def _make_user(
    display_name: str | None = None,
    gender: str | None = None,
) -> MagicMock:
    """Build a mock user with the given identity fields."""
    user = MagicMock()
    user.display_name = display_name
    user.gender = gender
    user.data = {}
    return user


def _make_owner(user: MagicMock | None = None) -> MagicMock:
    """Build a minimal mock owner with the given user attached."""
    owner = MagicMock()
    owner.user = user
    return owner


# ── Regression test for the original bug ──────────────────────
def test_two_different_users_produce_different_blocks() -> None:
    """Two owners with different users must get distinct identity blocks.
    """
    user_a = _make_user(
        display_name="Alice",
        gender="she/her",
    )
    user_b = _make_user(
        display_name="Bob",
        gender="he/him",
    )
    block_a = user_identity_part(
        _make_owner(user_a), LLMActionType.CHAT
    )
    block_b = user_identity_part(
        _make_owner(user_b), LLMActionType.CHAT
    )
    assert block_a is not None
    assert block_b is not None
    # Owner A's fields appear, owner B's do not
    assert "Alice" in block_a
    assert "she/her" in block_a
    assert "Bob" not in block_a
    assert "he/him" not in block_a
    # Owner B's fields appear, owner A's do not
    assert "Bob" in block_b
    assert "he/him" in block_b
    assert "Alice" not in block_b
    assert "she/her" not in block_b


# ── Composition cases ─────────────────────────────────────────
def test_all_fields_present() -> None:
    """All fields produce a block with content lines."""
    user = _make_user(
        display_name="Carol",
        gender="they/them",
    )
    block = user_identity_part(
        _make_owner(user), LLMActionType.CHAT
    )
    assert block is not None
    assert "[Who you're talking to]" in block
    assert "Their name: Carol" in block
    assert "they/them" in block


def test_name_only() -> None:
    """Name alone produces a single-line identity block."""
    user = _make_user(display_name="Dave")
    block = user_identity_part(
        _make_owner(user), LLMActionType.CHAT
    )
    assert block is not None
    assert "Their name: Dave" in block
    assert "gender" not in block


def test_gender_only() -> None:
    """Gender alone produces a single-line identity block."""
    user = _make_user(gender="she/her")
    block = user_identity_part(
        _make_owner(user), LLMActionType.CHAT
    )
    assert block is not None
    assert "she/her" in block
    assert "Their name:" not in block


# ── No-user / no-fields / wrong-action cases ─────────────────
def test_owner_has_no_user_returns_none() -> None:
    """An owner without a .user attribute yields None."""
    owner = MagicMock()
    del owner.user
    block = user_identity_part(owner, LLMActionType.CHAT)
    assert block is None


def test_no_fields_set_returns_none() -> None:
    """A user with no identity fields set yields None."""
    user = _make_user()
    block = user_identity_part(
        _make_owner(user), LLMActionType.CHAT
    )
    assert block is None


def test_non_conversational_action_returns_none() -> None:
    """Identity block is suppressed for non-conversational actions."""
    user = _make_user(
        display_name="Frank",
        gender="he/him",
    )
    block = user_identity_part(
        _make_owner(user), LLMActionType.SUMMARIZE,
    )
    assert block is None
