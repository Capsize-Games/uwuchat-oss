"""API-backed evals for baseline LLM agent flow via the Docker server.

These tests validate the basic request/response paths through the
running Docker API server — no local daemon subprocess is started.
"""

from __future__ import annotations

import pytest

from rag_eval_support import (
    assert_success,
    llm_chat_sync,
    resolve_active_model,
)


class TestAgentSimpleChatFlow:
    """Validate the no-tool chat path."""

    @pytest.mark.eval
    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.timeout(600)
    def test_agent_simple_chat_response(self) -> None:
        """LLM should produce a non-empty response."""
        model = resolve_active_model()
        messages = [
            {
                "role": "user",
                "content": "Say the word alpha and nothing else.",
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
        ), f"Expected 'alpha' in response, got: {result.text[:300]}"


class TestAgentConstrainedOutput:
    """Validate constrained numeric outputs."""

    @pytest.mark.eval
    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.timeout(600)
    def test_agent_outputs_single_digit(self) -> None:
        """LLM should include '7' in its response."""
        model = resolve_active_model()
        messages = [
            {
                "role": "user",
                "content": "What is 3 + 4? Reply with just the number.",
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
            "7" in text
        ), f"Expected '7' in response, got: {result.text[:300]}"

    @pytest.mark.eval
    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.timeout(600)
    def test_agent_outputs_constrained_word(self) -> None:
        """LLM should produce 'hello' somewhere in the response."""
        model = resolve_active_model()
        messages = [
            {
                "role": "user",
                "content": "Say hello.",
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
            "hello" in result.text.lower()
        ), f"Expected 'hello' in response, got: {result.text[:300]}"
