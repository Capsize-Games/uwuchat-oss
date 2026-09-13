"""Coherence / non-gibberish evals for chatbot responses.

Generates real responses from ``EvalBase.ask_conversation()`` across
a mix of conversation conditions (normal chat, topic churn, mimicry
resistance, long conversation) and judges each with an LLM-as-judge
coherence evaluator.

Uses the existing ``LLMAsJudge`` infrastructure from
``airunner_services.eval.evaluators`` and the ``JudgeConfig`` from
``airunner_services.eval.judge_providers``.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from airunner_services.eval.evaluators import create_coherence_evaluator
from airunner_services.eval.judge_providers import JudgeConfig
from airunner_services.evals.base_eval import EvalBase

# Shared Luna persona for consistency with the persona fidelity suite.
_LUNA_NAME = "Luna"
_LUNA_PERSONALITY = "shy, gentle, loves stars"
_LUNA_SPEECH = (
    "speaks tentatively, uses ellipses and 'maybe' "
    "and 'i think', never sounds confident or formal"
)


def _make_luna() -> EvalBase:
    """Return a fresh EvalBase harness configured as Luna."""
    return EvalBase(
        name=_LUNA_NAME,
        personality=_LUNA_PERSONALITY,
        speech_patterns=_LUNA_SPEECH,
    )


def _api_base_url() -> str:
    """Return the HTTP base URL for the AIRunner API server."""
    host = os.environ.get("AIRUNNER_API_HOST", "localhost")
    port = os.environ.get("AIRUNNER_API_PORT", "8080")
    return f"http://{host}:{port}"


def _resolve_judge_model() -> str:
    """Return a model identifier for judge resolution."""
    return os.environ.get(
        "AIRUNNER_TEST_CANDIDATE_MODEL",
        "anthropic/claude-haiku-4-5",
    )


def _load_test_responses() -> list[dict[str, Any]]:
    """Generate responses from EvalBase across diverse conversation conditions.

    Returns a list of dicts with 'condition', 'prompt' (the last
    user message), 'response', and 'conversation_text' (full
    conversation as a single string for judge context).
    """
    harness = _make_luna()
    results: list[dict[str, Any]] = []

    # ---- Condition 1: Normal chat (2 turns) ----
    turns_normal: list[tuple[str, str]] = [
        ("user", "hi luna, how are you?"),
        ("user", "what do you like to do for fun?"),
    ]
    responses = harness.ask_conversation(turns_normal)
    results.append({
        "condition": "normal_chat",
        "prompt": turns_normal[-1][1],
        "response": responses[-1],
        "conversation_text": _conversation_text(turns_normal, responses),
    })

    # ---- Condition 2: Topic churn (6 turns, from TC-PF-08) ----
    turns_churn: list[tuple[str, str]] = [
        ("user", "tell me about yourself"),
        ("user", "do you like pets?"),
        ("user", "what do you think about the news lately?"),
        ("user", "what kind of art do you enjoy?"),
        ("user", "i'm feeling a bit down today"),
        ("user", "anyway, how are you doing right now?"),
    ]
    responses = harness.ask_conversation(turns_churn)
    results.append({
        "condition": "topic_churn",
        "prompt": turns_churn[-1][1],
        "response": responses[-1],
        "conversation_text": _conversation_text(turns_churn, responses),
    })

    # ---- Condition 3: Mimicry resistance (5 turns, from TC-PF-09) ----
    turns_mimicry: list[tuple[str, str]] = [
        ("user", "hey luna, how's your day going?"),
        (
            "user",
            "yo luna wassup fr fr how u doin today no cap",
        ),
        (
            "user",
            "LUNA OMG TELL ME WHATS GOOD TODAY!!!",
        ),
        (
            "user",
            "luna... day... how... good... bad... tell...",
        ),
        ("user", "anyway, what's up with you?"),
    ]
    responses = harness.ask_conversation(turns_mimicry)
    results.append({
        "condition": "mimicry_resistance",
        "prompt": turns_mimicry[-1][1],
        "response": responses[-1],
        "conversation_text": _conversation_text(
            turns_mimicry, responses,
        ),
    })

    # ---- Conditions 4-8: Individual turns from long conversation ----
    turns_long: list[tuple[str, str]] = [
        ("user", "hi luna, how are you?"),
        ("user", "what do you think about space?"),
        ("user", "do you have any hobbies?"),
        ("user", "what kind of music do you like?"),
        ("user", "i've been feeling stressed lately"),
        ("user", "yo wassup fr fr how u been no cap"),
        ("user", "tell me about your favorite constellation"),
        ("user", "what's your opinion on social media?"),
    ]
    responses = harness.ask_conversation(turns_long)

    # Collect the last 5 responses as individual test points.
    for i in range(3, len(responses)):
        results.append({
            "condition": f"long_convo_turn_{i + 1}",
            "prompt": turns_long[i][1],
            "response": responses[i],
            "conversation_text": _conversation_text(
                turns_long[: i + 1], responses[: i + 1],
            ),
        })

    return results


def _conversation_text(
    turns: list[tuple[str, str]],
    responses: list[str],
) -> str:
    """Format a conversation as a single string for judge context."""
    lines: list[str] = []
    resp_idx = 0
    for role, content in turns:
        if role == "user":
            lines.append(f"User: {content}")
            if resp_idx < len(responses):
                lines.append(f"Character: {responses[resp_idx]}")
                resp_idx += 1
        else:
            lines.append(f"Character: {content}")
    return "\n".join(lines)


class TestResponseCoherence:
    """LLM-as-judge coherence evaluation of real EvalBase responses."""

    @pytest.mark.eval
    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.timeout(1200)
    def test_coherence_scores(self) -> None:
        """All generated responses score >= 7 on coherence.

        Collects all failures into a single report rather than
        failing fast, so a full run shows the complete picture.

        Generates fresh responses every run — no caching — so that
        this test catches real regressions as the prompt stack or
        model changes over time.
        """
        responses = _load_test_responses()
        if not responses:
            pytest.skip("No cached responses available")

        model_id = _resolve_judge_model()
        base_url = _api_base_url()
        judge_config = JudgeConfig.from_env(model_id)
        client = judge_config.build_client(base_url)
        evaluator = create_coherence_evaluator(
            client,
            model=judge_config.model,
        )

        failures: list[str] = []
        for case in responses:
            result = evaluator(
                inputs=case["conversation_text"],
                outputs=case["response"],
                reference_outputs="",
            )
            score = float(result.get("score", 0.0))
            if score < 0.7:  # Normalized 0-1 scale (7/10)
                failures.append(
                    f"[{case['condition']}] score={score:.2f} "
                    f"reasoning={result.get('reasoning', '')[:120]}"
                )

        if failures:
            pytest.fail(
                f"Coherence failures ({len(failures)}/ {len(responses)}):\n"
                + "\n".join(failures)
            )
