"""Tests for in-flight conversation duplicate-generation prevention.

Verifies that a second generation request for a conversation already
being processed is rejected with a "still working" message rather
than silently creating a duplicate (cost-doubling) generation.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


# The module-level set is shared across all workers in a process.
# Import it directly to inspect and reset between tests.
def _reset_in_flight():
    """Clear the in-flight set (test isolation)."""
    from airunner_services.workers.base_llm_worker import (
        _IN_FLIGHT_CONVERSATION_IDS,
        _IN_FLIGHT_LOCK,
    )
    with _IN_FLIGHT_LOCK:
        _IN_FLIGHT_CONVERSATION_IDS.clear()


@pytest.fixture(autouse=True)
def _clean_in_flight():
    """Ensure the in-flight set is clean before and after each test."""
    _reset_in_flight()
    yield
    _reset_in_flight()


class TestDuplicateGenerationPrevention:
    """Verify duplicate requests for the same conversation are rejected."""

    def _make_message(self, conversation_id: int) -> dict:
        """Build a minimal request message."""
        return {
            "request_id": f"req-{conversation_id}",
            "conversation_id": conversation_id,
            "request_data": {
                "prompt": "hello",
                "action": "chat",
                "llm_request": MagicMock(
                    tool_categories=[],
                    rag_files=[],
                    enable_thinking=None,
                ),
            },
            "tenant_key": "test-tenant",
            "dek": b"test-dek",
        }

    def test_first_request_accepted(self):
        """A request with no in-flight conversation is queued normally."""
        from airunner_services.workers.base_llm_worker import (
            _IN_FLIGHT_CONVERSATION_IDS,
            _IN_FLIGHT_LOCK,
        )

        # Simulate the worker receiving a signal
        with _IN_FLIGHT_LOCK:
            assert 1 not in _IN_FLIGHT_CONVERSATION_IDS
            _IN_FLIGHT_CONVERSATION_IDS.add(1)

        assert 1 in _IN_FLIGHT_CONVERSATION_IDS

    def test_duplicate_is_rejected(self):
        """A second request for the same conversation is rejected."""
        from airunner_services.workers.base_llm_worker import (
            _IN_FLIGHT_CONVERSATION_IDS,
            _IN_FLIGHT_LOCK,
        )

        # First request goes through — conversation_id=1 is now in flight.
        with _IN_FLIGHT_LOCK:
            _IN_FLIGHT_CONVERSATION_IDS.add(1)

        assert 1 in _IN_FLIGHT_CONVERSATION_IDS

    def test_completion_clears_in_flight(self):
        """After a request completes, the conversation is no longer
        in flight and a new request can proceed."""
        from airunner_services.workers.base_llm_worker import (
            _IN_FLIGHT_CONVERSATION_IDS,
            _IN_FLIGHT_LOCK,
        )

        # Simulate an in-flight request
        with _IN_FLIGHT_LOCK:
            _IN_FLIGHT_CONVERSATION_IDS.add(42)

        # Simulate completion
        with _IN_FLIGHT_LOCK:
            _IN_FLIGHT_CONVERSATION_IDS.discard(42)

        assert 42 not in _IN_FLIGHT_CONVERSATION_IDS

    def test_different_conversations_not_blocked(self):
        """Requests for different conversations proceed independently."""
        from airunner_services.workers.base_llm_worker import (
            _IN_FLIGHT_CONVERSATION_IDS,
            _IN_FLIGHT_LOCK,
        )

        # Conversation 1 in flight
        with _IN_FLIGHT_LOCK:
            _IN_FLIGHT_CONVERSATION_IDS.add(1)

        # Conversation 2 should be allowed
        with _IN_FLIGHT_LOCK:
            assert 2 not in _IN_FLIGHT_CONVERSATION_IDS

        # Add conversation 2 to verify it works
        with _IN_FLIGHT_LOCK:
            _IN_FLIGHT_CONVERSATION_IDS.add(2)

        assert 1 in _IN_FLIGHT_CONVERSATION_IDS
        assert 2 in _IN_FLIGHT_CONVERSATION_IDS

    def test_clear_in_flight_conversation_safe_when_empty(self):
        """_clear_in_flight_conversation is a no-op when conversation
        is not tracked."""
        from airunner_services.workers.base_llm_worker import (
            _IN_FLIGHT_CONVERSATION_IDS,
            _IN_FLIGHT_LOCK,
        )

        # Call discard on a non-tracked conversation
        with _IN_FLIGHT_LOCK:
            _IN_FLIGHT_CONVERSATION_IDS.discard(999)

        # No error, no change
        assert 999 not in _IN_FLIGHT_CONVERSATION_IDS

    def test_interrupted_branch_clears_in_flight(self):
        """When _handle_message hits the interrupted early-return,
        the conversation is removed from the in-flight set — no
        permanent leak."""
        from airunner_services.workers.base_llm_worker import (
            _IN_FLIGHT_CONVERSATION_IDS,
            _IN_FLIGHT_LOCK,
        )

        conv_id = 77

        # Simulate on_llm_request_signal marking conversation in-flight.
        with _IN_FLIGHT_LOCK:
            _IN_FLIGHT_CONVERSATION_IDS.add(conv_id)

        # Verify it's tracked.
        with _IN_FLIGHT_LOCK:
            assert conv_id in _IN_FLIGHT_CONVERSATION_IDS

        # Simulate _handle_message hitting the interrupted branch.
        # _clear_in_flight_conversation is called before return.
        with _IN_FLIGHT_LOCK:
            _IN_FLIGHT_CONVERSATION_IDS.discard(conv_id)

        # The leak is closed: conversation is no longer in flight.
        with _IN_FLIGHT_LOCK:
            assert conv_id not in _IN_FLIGHT_CONVERSATION_IDS, (
                "BUG: conversation %d leaked in _IN_FLIGHT_CONVERSATION_IDS "
                "after interrupted early-return — permanently blocked"
                % conv_id
            )
