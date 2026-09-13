"""Tests that ``set_code_mode`` enqueues the GPU switch task.

The GPU switch is fire-and-forget (Decision C): ``set_code_mode`` must
persist the code-mode state AND enqueue the Celery task with the right
argument, without blocking on the multi-second daemon swap. All DB and
Celery interactions are mocked — no real database or broker.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from projects.uwuchat.server import code_mode_service as mod


def _conversation(code_mode: bool = False) -> MagicMock:
    """Return a fake Conversation with the given code_mode state."""
    conv = MagicMock()
    conv.user_data = {"code_mode": code_mode}
    return conv


def test_set_code_mode_enqueues_switch_when_enabled() -> None:
    """Enabling code mode enqueues the GPU switch with enabled=True."""
    conv = _conversation(code_mode=False)
    with patch.object(
        mod.Conversation.objects, "get", return_value=conv,
    ), patch.object(
        mod.Conversation.objects, "update", return_value=True,
    ) as update, patch(
        "projects.uwuchat.server.tasks.gpu_inference_tasks"
        ".apply_code_mode_gpu_switch.apply_async",
    ) as apply_async:
        enabled, _slug = mod.set_code_mode(7, True)

    assert enabled is True
    assert conv.user_data["code_mode"] is True
    update.assert_called_once()
    apply_async.assert_called_once_with(args=[True])


def test_set_code_mode_enqueues_switch_when_disabled() -> None:
    """Disabling code mode enqueues the GPU switch with enabled=False."""
    conv = _conversation(code_mode=True)
    with patch.object(
        mod.Conversation.objects, "get", return_value=conv,
    ), patch.object(
        mod.Conversation.objects, "update", return_value=True,
    ), patch(
        "projects.uwuchat.server.tasks.gpu_inference_tasks"
        ".apply_code_mode_gpu_switch.apply_async",
    ) as apply_async:
        enabled, _slug = mod.set_code_mode(7, False)

    assert enabled is False
    assert conv.user_data["code_mode"] is False
    apply_async.assert_called_once_with(args=[False])


def test_set_code_mode_never_raises_on_broker_error() -> None:
    """A broker failure to enqueue must not break the toggle itself."""
    conv = _conversation(code_mode=False)
    with patch.object(
        mod.Conversation.objects, "get", return_value=conv,
    ), patch.object(
        mod.Conversation.objects, "update", return_value=True,
    ), patch(
        "projects.uwuchat.server.tasks.gpu_inference_tasks"
        ".apply_code_mode_gpu_switch.apply_async",
        side_effect=RuntimeError("broker down"),
    ):
        enabled, _slug = mod.set_code_mode(7, True)

    # The persisted state is correct even though enqueue failed.
    assert enabled is True
    assert conv.user_data["code_mode"] is True


def test_set_code_mode_invalid_slug_raises_before_enqueue() -> None:
    """An invalid slug raises ValueError and never enqueues."""
    with patch.object(
        mod.Conversation.objects, "get", return_value=_conversation(),
    ), patch(
        "projects.uwuchat.server.tasks.gpu_inference_tasks"
        ".apply_code_mode_gpu_switch.apply_async",
    ) as apply_async, pytest.raises(ValueError):
        mod.set_code_mode(7, True, slug="not-a-mode")

    apply_async.assert_not_called()
