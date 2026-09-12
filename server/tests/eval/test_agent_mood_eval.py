"""API-backed evals for LLM agent mood updates via the Docker server.

Tests validate that the LLM agent correctly updates conversation mood
after user interaction, tracked through the conversation metadata.
"""

from __future__ import annotations

import pytest

from rag_eval_support import (
    assert_success,
    create_conversation,
    delete_conversation,
    llm_chat_sync,
    resolve_active_model,
)

_MOOD_CASES = [
    pytest.param(
        "thanks, that was really helpful",
        id="happy-user",
    ),
    pytest.param(
        "this is stupid and I hate it",
        id="frustrated-user",
    ),
    pytest.param(
        "I am confused and do not understand what you mean",
        id="confused-user",
    ),
]


class TestAgentMoodResponse:
    """Validate LLM responds appropriately to different user moods."""

    @pytest.mark.eval
    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.timeout(600)
    @pytest.mark.parametrize("prompt", _MOOD_CASES)
    def test_agent_responds_to_emotional_prompt(
        self,
        prompt: str,
    ) -> None:
        """LLM should produce a non-empty response to an emotional prompt."""
        model = resolve_active_model()
        conversation_id = create_conversation()
        try:
            # Seed the conversation with a prior turn
            messages = [
                {"role": "user", "content": "Hello there."},
                {
                    "role": "assistant",
                    "content": "Hi! How can I help you?",
                },
                {"role": "user", "content": prompt},
            ]
            result = llm_chat_sync(
                messages,
                model=model,
                temperature=0.7,
                max_tokens=64,
                conversation_id=conversation_id,
            )
            assert_success(result)
            assert result.text, f"Empty response for mood prompt: '{prompt}'"
        finally:
            delete_conversation(conversation_id)

    @pytest.mark.eval
    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.timeout(600)
    def test_agent_maintains_conversation_context(self) -> None:
        """LLM should reference prior conversation context."""
        model = resolve_active_model()
        conversation_id = create_conversation()
        try:
            # First turn
            messages = [
                {
                    "role": "user",
                    "content": "My favorite color is blue.",
                },
            ]
            result1 = llm_chat_sync(
                messages,
                model=model,
                temperature=0.7,
                max_tokens=64,
                conversation_id=conversation_id,
            )
            assert_success(result1)
            # Second turn — ask about the previous info
            messages2 = [
                {"role": "user", "content": "What is my favorite color?"},
            ]
            result2 = llm_chat_sync(
                messages2,
                model=model,
                temperature=0.1,
                max_tokens=32,
                conversation_id=conversation_id,
            )
            assert_success(result2)
            # The response should mention blue
            text = result2.text.lower()
            assert (
                "blue" in text
            ), f"Expected 'blue' in response, got: {result2.text[:300]}"
        finally:
            delete_conversation(conversation_id)
