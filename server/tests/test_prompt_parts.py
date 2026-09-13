"""Unit tests for prompt-builder parts — Plan 3 disclaimer fix.

Tests that the hedging disclaimer is present in the output of
``_agent_memory_part`` when AgentMemory has content.
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

from airunner_services.llm.managers.prompt_builder.parts import (
    _agent_memory_part,
)


def test_agent_memory_includes_disclaimer() -> None:
    """_agent_memory_part output contains the AI-written-summary disclaimer."""
    owner = MagicMock()
    owner.chatbot = MagicMock()
    owner.chatbot.id = 1

    mock_row = MagicMock()
    mock_row.summary = "User likes coffee."
    mock_row.updated_at = "2026-07-01T12:00:00Z"

    with (
        patch(
            "airunner_services.database.models.agent_memory"
            ".AgentMemory",
        ) as agent_memory_cls,
        patch(
            "airunner_services.llm.managers.prompt_builder"
            ".upcoming_events.upcoming_events_block",
            return_value="",
        ),
    ):
        agent_memory_cls.objects.filter_by_first.return_value = mock_row
        result = _agent_memory_part(owner)
        assert result is not None
        assert "AI-written summary" in result
        assert "may contain imprecise" in result
        assert "sketch, not verbatim fact" in result
        assert "User likes coffee." in result
