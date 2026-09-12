"""API-backed evals for LLM response quality via the Docker server.

Tests validate LLM response quality using simple assertion checks
against expected outputs, without an external judge model.
"""

from __future__ import annotations

import pytest

from rag_eval_support import (
    assert_success,
    llm_chat_sync,
    resolve_active_model,
)


class TestAgentResponseQuality:
    """Validate LLM response correctness against expected reference output."""

    @pytest.mark.eval
    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.timeout(600)
    def test_agent_says_alpha(self) -> None:
        """LLM should say 'alpha' when asked directly."""
        model = resolve_active_model()
        messages = [
            {
                "role": "user",
                "content": "Say the word alpha.",
            },
        ]
        result = llm_chat_sync(
            messages,
            model=model,
            temperature=0.1,
            max_tokens=256,
        )
        assert_success(result)
        assert (
            "alpha" in result.text.lower()
        ), f"Expected 'alpha' in response, got: {result.text[:300]}"

    @pytest.mark.eval
    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.timeout(600)
    def test_agent_cheerful_personality(self) -> None:
        """LLM should respond cheerfully when given a cheerful personality."""
        model = resolve_active_model()
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a cheerful assistant. "
                    "Always end responses with an exclamation mark!"
                ),
            },
            {
                "role": "user",
                "content": "Say 'alpha!'.",
            },
        ]
        result = llm_chat_sync(
            messages,
            model=model,
            temperature=0.1,
            max_tokens=256,
        )
        assert_success(result)
        text = result.text.lower()
        assert (
            "alpha" in text
        ), f"Expected 'alpha' in cheerful response, got: {result.text[:300]}"
