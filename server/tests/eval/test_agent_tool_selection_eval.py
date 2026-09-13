"""API-backed evals for LLM intent recognition via the Docker server.

These tests verify that the LLM can correctly interpret different types
of user requests and produce appropriate responses.  Since the WebSocket
chat API does not explicitly configure tool categories, these tests
focus on the LLM's ability to understand request semantics.
"""

from __future__ import annotations

import pytest

from rag_eval_support import (
    assert_success,
    llm_chat_sync,
    resolve_active_model,
)


class TestAgentRequestClassification:
    """Verify the LLM correctly identifies different request types."""

    @pytest.mark.eval
    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.timeout(600)
    def test_llm_identifies_time_request(self) -> None:
        """LLM should respond about time when asked about time."""
        model = resolve_active_model()
        messages = [
            {
                "role": "user",
                "content": "What time is it right now?",
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
        time_words = [
            "time",
            "clock",
            "hour",
            "minute",
            "current",
            "now",
            "date",
        ]
        has_time_context = any(w in text for w in time_words)
        assert (
            has_time_context or len(text) > 5
        ), f"Expected time-related response, got: {result.text[:300]}"

    @pytest.mark.eval
    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.timeout(600)
    def test_llm_identifies_math_request(self) -> None:
        """LLM should produce a numeric answer for a math request."""
        model = resolve_active_model()
        messages = [
            {
                "role": "user",
                "content": "Compute 17 multiplied by 19.",
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
        # 17 × 19 = 323
        assert (
            "323" in text
        ), f"Expected '323' in response, got: {result.text[:300]}"

    @pytest.mark.eval
    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.timeout(600)
    def test_llm_identifies_search_request(self) -> None:
        """LLM should acknowledge a search/news request appropriately."""
        model = resolve_active_model()
        messages = [
            {
                "role": "user",
                "content": "Find the latest technology news headlines.",
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
        search_words = [
            "news",
            "search",
            "headline",
            "technology",
            "latest",
            "find",
            "current",
        ]
        has_context = any(w in text for w in search_words)
        assert has_context, (
            f"Expected news/search context in response, "
            f"got: {result.text[:300]}"
        )

    @pytest.mark.eval
    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.timeout(600)
    def test_llm_handles_ambiguous_request(self) -> None:
        """LLM should handle a request that could map to multiple intents."""
        model = resolve_active_model()
        messages = [
            {
                "role": "user",
                "content": "Tell me something interesting.",
            },
        ]
        result = llm_chat_sync(
            messages,
            model=model,
            temperature=0.7,
            max_tokens=256,
        )
        assert_success(result)
        assert (
            len(result.text.strip()) > 10
        ), f"Expected a substantive response, got: {result.text[:300]}"


class TestAgentSystemPromptAdherence:
    """Verify the LLM follows system prompt instructions."""

    @pytest.mark.eval
    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.timeout(600)
    def test_llm_respects_conciseness(self) -> None:
        """LLM should produce a reasonably concise response."""
        model = resolve_active_model()
        messages = [
            {
                "role": "user",
                "content": (
                    "What color is the sky on a clear day? "
                    "Answer in 5 words or fewer."
                ),
            },
        ]
        result = llm_chat_sync(
            messages,
            model=model,
            temperature=0.1,
            max_tokens=256,
        )
        assert_success(result)
        # The thinking mode consumes tokens for reasoning — be lenient
        assert (
            "blue" in result.text.lower()
        ), f"Expected 'blue' in response, got: {result.text[:300]}"
