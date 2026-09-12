"""Tests for ``code_mode_active_for_owner`` conversation-id resolution.

The LLM manager's own ``_conversation_id`` is never assigned — the real
per-conversation id lives on the workflow manager
(``WorkflowManager.set_conversation_id``). ``code_mode_active_for_owner``
must fall back to ``owner._workflow_manager._conversation_id`` exactly like
``prompt_builder/per_turn_bridge_retrieval.py`` does; without the fallback
it always returns False and the code-mode prompt/tool-binding never engages.

All DB interactions are mocked — no real database.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from projects.uwuchat.server import code_mode_service as mod


def _conversation(code_mode: bool = False) -> MagicMock:
    """Return a fake Conversation with the given code_mode state."""
    conv = MagicMock()
    conv.user_data = {"code_mode": code_mode}
    return conv


def _owner_with_workflow_conv_id(conv_id: int) -> MagicMock:
    """Return an owner whose workflow manager carries the conversation id."""
    owner = MagicMock()
    owner._conversation_id = None
    wm = MagicMock()
    wm._conversation_id = conv_id
    owner._workflow_manager = wm
    return owner


def test_owner_direct_conv_id_missing_falls_back_to_workflow_manager() -> None:
    """conv_id on the workflow manager is used when the owner's is None."""
    owner = _owner_with_workflow_conv_id(7)
    with patch.object(
        mod.Conversation.objects,
        "get",
        return_value=_conversation(code_mode=True),
    ) as get:
        result = mod.code_mode_active_for_owner(owner)

    assert result is True
    get.assert_called_once_with(7)


def test_fallback_conversation_with_code_mode_off_returns_false() -> None:
    """Fallback conv id with code_mode=False returns False."""
    owner = _owner_with_workflow_conv_id(7)
    with patch.object(
        mod.Conversation.objects,
        "get",
        return_value=_conversation(code_mode=False),
    ):
        result = mod.code_mode_active_for_owner(owner)

    assert result is False


def test_no_workflow_manager_returns_false_without_crash() -> None:
    """Missing workflow manager (and no direct id) returns False."""
    owner = MagicMock()
    owner._conversation_id = None
    owner._workflow_manager = None

    result = mod.code_mode_active_for_owner(owner)

    assert result is False


def test_direct_conv_id_still_works() -> None:
    """A directly-set owner._conversation_id still wins."""
    owner = MagicMock()
    owner._conversation_id = 7
    owner._workflow_manager = None
    with patch.object(
        mod.Conversation.objects,
        "get",
        return_value=_conversation(code_mode=True),
    ) as get:
        result = mod.code_mode_active_for_owner(owner)

    assert result is True
    get.assert_called_once_with(7)


def test_missing_conversation_returns_false() -> None:
    """A None conversation lookup returns False."""
    owner = _owner_with_workflow_conv_id(7)
    with patch.object(
        mod.Conversation.objects,
        "get",
        return_value=None,
    ):
        result = mod.code_mode_active_for_owner(owner)

    assert result is False
