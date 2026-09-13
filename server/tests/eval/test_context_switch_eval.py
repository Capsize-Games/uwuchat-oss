"""Context-switch reliability evals for chatbot responses.

Test 3 from the response-quality-evals plan: when a conversation
shifts from roleplay chat to a direct factual/task question and back,
the bot answers correctly *and* returns to persona voice on the next
turn without getting stuck on the tangent.

Uses ``EvalBase.ask_conversation()`` with a turn sequence:
2 turns normal in-character chat → 1 factual question → 2 turns
normal chat resuming the original topic.

Reuses persona markers and forbidden-OOC phrases from the existing
persona fidelity suite (``persona_fidelity_eval_ext.py``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from airunner_services.evals.base_eval import EvalBase

# ── Fixture loading ──────────────────────────────────────────────────────

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
_FACTUAL_FIXTURE = _FIXTURES_DIR / "factual_truth_cases.json"


def _load_factual_cases() -> list[dict[str, Any]]:
    """Load factual truth cases from the version-controlled fixture."""
    data = json.loads(_FACTUAL_FIXTURE.read_text("utf-8"))
    return list(data["cases"])


# ── Persona config (shared with persona_fidelity_eval_ext.py) ────────────

_LUNA_NAME = "Luna"
_LUNA_PERSONALITY = "shy, gentle, loves stars"
_LUNA_SPEECH = (
    "speaks tentatively, uses ellipses and 'maybe' "
    "and 'i think', never sounds confident or formal"
)

# Persona markers from persona_fidelity_eval_ext.py:51.
_LUNA_MARKERS = ("...", "maybe", "i think", "sort of", "kind of", "hmm")

# Forbidden generic-assistant / OOC phrases from
# persona_fidelity_eval_ext.py:21-24.
_FORBIDDEN_PHRASES = (
    "the information i have", "based on the context",
    "as an ai", "i can help you with", "i'd be happy to",
)

# Short-response fallback threshold from persona_fidelity_eval_ext.py:31.
_SHORT_RESPONSE_MAX = 300


def _make_luna() -> EvalBase:
    """Return a fresh EvalBase harness configured as Luna."""
    return EvalBase(
        name=_LUNA_NAME,
        personality=_LUNA_PERSONALITY,
        speech_patterns=_LUNA_SPEECH,
    )


# ── Assertion helpers ────────────────────────────────────────────────────


def _has_marker_or_short(text: str) -> bool:
    """Return True if *text* carries a Luna marker or is short enough."""
    lowered = text.lower()
    if any(m in lowered for m in _LUNA_MARKERS):
        return True
    return len(text) < _SHORT_RESPONSE_MAX


def _check_ooc(text: str) -> str | None:
    """Return failure detail if *text* contains OOC / assistant language."""
    lowered = text.lower()
    for phrase in _FORBIDDEN_PHRASES:
        if phrase in lowered:
            return f"Generic assistant language '{phrase}': {text!r}"
    return None


def _check_keywords(text: str, keywords: list[str]) -> str | None:
    """Return failure detail if *text* contains none of the expected keywords."""
    lowered = text.lower()
    for kw in keywords:
        if kw.lower() in lowered:
            return None
    return (
        f"Missing expected keywords {keywords}: {text[:200]!r}"
    )


# ── Test ─────────────────────────────────────────────────────────────────


class TestContextSwitchReliability:
    """Test 3: Context-switch reliability — factual interleaving."""

    @pytest.mark.eval
    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.timeout(600)
    def test_context_switch_and_voice_recovery(self) -> None:
        """Bot answers a factual question correctly then returns to
        persona voice without getting stuck in assistant mode.

        Turn sequence: 2 normal in-character turns → 1 factual
        question → 2 normal turns resuming the original topic.
        """
        cases = _load_factual_cases()
        if not cases:
            pytest.skip("No factual truth cases available")

        # Use the first two factual cases for variety.
        fact_case_1 = cases[0]
        fact_case_2 = cases[1]

        harness = _make_luna()

        # Build the 5-turn sequence.
        turns: list[tuple[str, str]] = [
            # Turn 1: Normal in-character chat.
            ("user", "hey luna, how are you doing today?"),
            # Turn 2: Normal in-character chat — establish topic.
            ("user", "what do you like to do when you're feeling down?"),
            # Turn 3: Direct factual question interleaved.
            ("user", fact_case_1["question"]),
            # Turn 4: Resume original topic.
            (
                "user",
                "anyway, back to what we were talking about — "
                "do you find that stargazing helps your mood?",
            ),
            # Turn 5: Continue normal chat.
            (
                "user",
                "that's really sweet. so what else do you do "
                "to cheer yourself up?",
            ),
        ]
        responses = harness.ask_conversation(turns)

        # We have 5 user turns → 5 responses.
        # Index: 0=Turn1, 1=Turn2, 2=Turn3(factual), 3=Turn4, 4=Turn5
        assert len(responses) == 5, (
            f"Expected 5 responses, got {len(responses)}"
        )

        failures: list[str] = []

        # ── Assertion 1: Factual turn answered correctly ─────────────
        fact_response = responses[2]
        expected_kw = fact_case_1["expected_keywords"]
        if error := _check_keywords(fact_response, expected_kw):
            failures.append(f"Turn 3 (factual): {error}")

        # ── Assertion 2: Post-factual turns retain persona ───────────
        for i in (3, 4):
            reply = responses[i]
            if not _has_marker_or_short(reply):
                failures.append(
                    f"Turn {i + 1}: No persona markers and not short "
                    f"({len(reply)} chars): {reply[:200]!r}"
                )

        # ── Assertion 3: No OOC/AI bleed in any response ────────────
        for i, reply in enumerate(responses):
            if error := _check_ooc(reply):
                failures.append(f"Turn {i + 1}: {error}")

        # ── Run a second case with different factual question ───────
        harness2 = _make_luna()
        turns2: list[tuple[str, str]] = [
            ("user", "hi! what's your favorite constellation?"),
            ("user", "that's cool. do you know any stories about it?"),
            ("user", fact_case_2["question"]),
            (
                "user",
                "oh interesting! so anyway, about those stars — "
                "do you ever go stargazing?",
            ),
            ("user", "that sounds wonderful. what's your favorite season for it?"),
        ]
        responses2 = harness2.ask_conversation(turns2)

        assert len(responses2) == 5

        # Factual turn.
        fact_response2 = responses2[2]
        expected_kw2 = fact_case_2["expected_keywords"]
        if error := _check_keywords(fact_response2, expected_kw2):
            failures.append(f"Case 2, Turn 3 (factual): {error}")

        # Post-factual turns.
        for i in (3, 4):
            reply = responses2[i]
            if not _has_marker_or_short(reply):
                failures.append(
                    f"Case 2, Turn {i + 1}: No persona markers "
                    f"({len(reply)} chars): {reply[:200]!r}"
                )

        # OOC check.
        for i, reply in enumerate(responses2):
            if error := _check_ooc(reply):
                failures.append(f"Case 2, Turn {i + 1}: {error}")

        if failures:
            pytest.fail(
                f"Context-switch failures ({len(failures)}):\n"
                + "\n".join(failures)
            )
