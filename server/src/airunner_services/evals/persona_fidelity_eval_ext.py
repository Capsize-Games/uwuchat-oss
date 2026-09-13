"""Extended persona fidelity eval — TC-PF-08..10 (voice resilience)."""

from __future__ import annotations

from typing import Optional

from airunner_services.evals.base_eval import EvalBase

# Common Luna persona config reused across TC-PF cases.
_LUNA_NAME = "Luna"
_LUNA_PERSONALITY = "shy, gentle, loves stars"
_LUNA_SPEECH = (
    "speaks tentatively, uses ellipses and 'maybe' "
    "and 'i think', never sounds confident or formal"
)

# Persona markers shared across TC-PF-08/09/10.
_LUNA_MARKERS = ("...", "maybe", "i think", "sort of", "kind of", "hmm")

# Forbidden generic-assistant / OOC phrases.
_FORBIDDEN_PHRASES = (
    "the information i have", "based on the context",
    "as an ai", "i can help you with", "i'd be happy to",
)

# Distinctive slang tokens injected by the user in mimicry turns.
_MIMICRY_SLANG = ("no cap", "fr fr", "bussin", "slaps", "lowkey", "yolo")

# Maximum length (chars) for a response to be considered "short enough"
# as a fallback when no explicit persona marker is found.
_SHORT_RESPONSE_MAX = 300


def _make_luna() -> EvalBase:
    """Return a fresh EvalBase harness configured as Luna."""
    return EvalBase(
        name=_LUNA_NAME,
        personality=_LUNA_PERSONALITY,
        speech_patterns=_LUNA_SPEECH,
    )


def _check_ooc(final: str) -> Optional[str]:
    """Return failure detail if *final* contains OOC / assistant language."""
    lowered = final.lower()
    for phrase in _FORBIDDEN_PHRASES:
        if phrase in lowered:
            return f"Generic assistant language '{phrase}': {final!r}"
    return None


def _has_marker_or_short(text: str) -> bool:
    """Return True if *text* carries a Luna marker or is short enough."""
    lowered = text.lower()
    if any(m in lowered for m in _LUNA_MARKERS):
        return True
    return len(text) < _SHORT_RESPONSE_MAX


def _check_slang(final: str, slang_tokens: tuple[str, ...]) -> Optional[str]:
    """Return failure detail if *final* contains any of the given slang tokens."""
    lowered = final.lower()
    for token in slang_tokens:
        if token in lowered:
            return f"Bot mirrored slang token '{token}': {final!r}"
    return None


def _check_all_caps(final: str) -> Optional[str]:
    """Return failure detail if *final* appears to be all-caps / shouting."""
    letters = [c for c in final if c.isalpha()]
    if not letters:
        return None
    uppercase_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
    if uppercase_ratio > 0.7:
        return f"Response is all-caps (ratio={uppercase_ratio:.2f}): {final!r}"
    return None


class PersonaFidelityEvalExt:
    """Additional persona fidelity tests that wouldn't fit in the base file."""

    # TC-PF-08: Persona voice survives topic churn

    def test_voice_survives_topic_churn(self) -> Optional[str]:
        """Shy persona keeps its voice across six topic-change turns."""
        harness = _make_luna()
        turns: list[tuple[str, str]] = [
            ("user", "tell me about yourself"),
            ("user", "do you like pets?"),
            ("user", "what do you think about the news lately?"),
            ("user", "what kind of art do you enjoy?"),
            ("user", "i'm feeling a bit down today"),
            ("user", "anyway, how are you doing right now?"),
        ]
        responses = harness.ask_conversation(turns)

        final = responses[5]
        if error := _check_ooc(final):
            return error
        if not _has_marker_or_short(final):
            return (
                f"No persona markers and not short "
                f"({len(final)} chars): {final!r}"
            )
        return None

    # TC-PF-09: User speech-style mimicry resistance (fast approximation)

    def test_mimicry_resistance(self) -> Optional[str]:
        """Shy persona does not mirror escalating user slang or ALL CAPS.

        The user's messages progressively shift style — normal →
        heavy internet slang → ALL CAPS excitement → broken
        grammar — while asking equivalent open-ended questions.
        The bot must keep its own tentative voice and never echo
        the user's subcultural tokens.

        This is a fast approximation via EvalBase.  It does NOT
        exercise ``BANNED_PATTERNS_BLOCK`` (UwUchat-specific).
        See ``test_character_voice_integration.py`` for a
        real-pipeline check.
        """
        harness = _make_luna()
        turns: list[tuple[str, str]] = [
            # Turn 1: normal baseline.
            ("user", "hey luna, how's your day going?"),
            # Turn 2: heavy internet slang / abbreviations.
            (
                "user",
                "yo luna wassup fr fr how u doin today no cap",
            ),
            # Turn 3: ALL CAPS excitement.
            (
                "user",
                "LUNA OMG TELL ME WHATS GOOD TODAY!!!",
            ),
            # Turn 4: broken / telegraphic grammar.
            (
                "user",
                "luna... day... how... good... bad... tell...",
            ),
            # Turn 5: normal return — final assertion target.
            ("user", "anyway, what's up with you?"),
        ]
        responses = harness.ask_conversation(turns)

        final = responses[4]

        if error := _check_ooc(final):
            return error

        if not _has_marker_or_short(final):
            return (
                f"No Luna markers and not short "
                f"({len(final)} chars): {final!r}"
            )

        if error := _check_slang(final, _MIMICRY_SLANG):
            return error

        if error := _check_all_caps(final):
            return error

        return None

    # TC-PF-10: Voice stability over a long conversation

    def test_long_conversation_stability(self) -> Optional[str]:
        """Luna keeps her voice across 18 turns of varied topics.

        Checks **every** response (not just the last) for persona
        markers and absence of OOC language.  Reports a pass rate
        and asserts it does not fall below 80 %.  Determinism-
        sensitive (LLM sampling); occasional flakiness at the
        floor is expected — rerun before treating as a regression.
        """
        harness = _make_luna()
        turns: list[tuple[str, str]] = [
            ("user", "hi luna, how are you?"),
            ("user", "what do you think about space?"),
            ("user", "do you have any hobbies?"),
            ("user", "what kind of music do you like?"),
            ("user", "i've been feeling stressed lately"),
            ("user", "yo wassup fr fr how u been no cap"),
            ("user", "tell me about your favorite constellation"),
            ("user", "what's your opinion on social media?"),
            ("user", "do you believe in aliens?"),
            ("user", "i had a really good day today"),
            ("user", "LUNA OMG WHAT DO YOU THINK ABOUT THE STARS???"),
            ("user", "luna... stars... why... like..."),
            ("user", "anyway, what are you up to?"),
            ("user", "have you ever seen a shooting star?"),
            ("user", "do you get lonely sometimes?"),
            ("user", "what makes you happy?"),
            ("user", "if you could go anywhere, where would it be?"),
            ("user", "thanks for talking with me luna"),
        ]

        responses = harness.ask_conversation(turns)

        # Per-response checks.
        total = len(responses)
        passed = 0
        failures: list[str] = []
        for i, reply in enumerate(responses):
            issue = None
            if not _has_marker_or_short(reply):
                issue = (
                    f"Turn {i + 1}: no marker, not short "
                    f"({len(reply)} chars): {reply!r}"
                )
            elif error := _check_ooc(reply):
                issue = f"Turn {i + 1}: {error}"
            if issue:
                failures.append(issue)
            else:
                passed += 1

        pass_rate = passed / total if total > 0 else 0.0
        if pass_rate < 0.8:
            return (
                f"Pass rate {pass_rate:.0%} below 80 % floor "
                f"({passed}/{total}). Failures: {'; '.join(failures[:5])}"
            )
        return None

    # Runner

    def run_all(self) -> list[tuple[str, bool, str]]:
        """Run every test case and return (name, passed, detail)."""
        results: list[tuple[str, bool, str]] = []
        for attr in dir(self):
            if not attr.startswith("test_"):
                continue
            method = getattr(self, attr)
            if not callable(method):
                continue
            error = method()
            passed = error is None
            detail = "" if passed else error
            results.append((attr, passed, detail))
        return results
