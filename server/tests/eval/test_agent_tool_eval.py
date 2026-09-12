"""API-backed evals for LLM capability probes via the Docker server.

These tests verify that the LLM can handle tasks that would normally
require tools (math, datetime, etc.) through direct inference.  Since
the WebSocket chat API does not explicitly configure tool availability,
these tests probe the LLM's native capabilities.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from rag_eval_support import (
    assert_success,
    llm_chat_sync,
    resolve_active_model,
)


class TestAgentMathCapability:
    """Verify the LLM can perform arithmetic through direct inference."""

    @pytest.mark.eval
    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.timeout(600)
    def test_llm_multiplies_two_numbers(self) -> None:
        """LLM should compute 12 × 13 = 156."""
        model = resolve_active_model()
        messages = [
            {
                "role": "user",
                "content": "What is 12 * 13? Answer with just the number.",
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
            "156" in text
        ), f"Expected '156' in response, got: {result.text[:300]}"

    @pytest.mark.eval
    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.timeout(600)
    def test_llm_computes_exponentiation(self) -> None:
        """LLM should compute 6^4 = 1296."""
        model = resolve_active_model()
        messages = [
            {
                "role": "user",
                "content": "What is 6 to the power of 4? Answer with just the number.",
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
            "1296" in text
        ), f"Expected '1296' in response, got: {result.text[:300]}"


class TestAgentDatetimeCapability:
    """Verify the LLM can reason about dates and times."""

    @pytest.mark.eval
    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.timeout(600)
    def test_llm_identifies_current_year(self) -> None:
        """LLM should know or estimate the current year."""
        model = resolve_active_model()
        current_year = str(datetime.now().astimezone().year)
        messages = [
            {
                "role": "user",
                "content": "What year is it right now? Answer with just the year.",
            },
        ]
        result = llm_chat_sync(
            messages,
            model=model,
            temperature=0.1,
            max_tokens=256,
        )
        assert_success(result)
        text = result.text
        # Allow the current year or a nearby year (knowledge cutoff)
        year_int = int(current_year)
        ok_years = {str(y) for y in range(year_int - 2, year_int + 2)}
        found = any(y in text for y in ok_years)
        assert (
            found
        ), f"Expected year near {current_year}, got: {result.text[:300]}"


class TestAgentGeneralKnowledge:
    """Verify the LLM can answer general knowledge questions."""

    @pytest.mark.eval
    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.timeout(600)
    def test_llm_answers_factual_question(self) -> None:
        """LLM should answer a simple factual question correctly."""
        model = resolve_active_model()
        messages = [
            {
                "role": "user",
                "content": "What is the capital of France?",
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
            "paris" in result.text.lower()
        ), f"Expected 'Paris' in response, got: {result.text[:300]}"

    @pytest.mark.eval
    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.timeout(600)
    def test_llm_counts_accurately(self) -> None:
        """LLM should produce numbers one through three."""
        model = resolve_active_model()
        messages = [
            {
                "role": "user",
                "content": "Count from one to three. Say 'one two three'.",
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
        has_all = all(w in text for w in ["one", "two", "three"])
        assert (
            has_all
        ), f"Expected 'one two three' in response, got: {result.text[:300]}"
