"""Assertion-based memory coherence evals for UwUchat roleplaying bots."""

from __future__ import annotations

from typing import Optional

from airunner_services.evals.base_eval import EvalBase


class MemoryCoherenceEval:
    """Runs memory coherence test cases against the LLM.

    Each test case provides pre-written memory (AgentMemory.summary
    or episodic bullets) and verifies the bot references it correctly.
    """

    # ------------------------------------------------------------------
    # TC-MC-01: Rolling memory recall — user preference
    # ------------------------------------------------------------------

    def test_recall_user_preference(self) -> Optional[str]:
        """Assert the bot recalls a user preference from memory summary."""
        harness = EvalBase(
            name="Nova",
            personality="warm, attentive, loves deep conversations",
            memory_summary=(
                "The user told me their favourite colour is violet "
                "and they hate mornings. We talked about stargazing "
                "together."
            ),
        )
        response = harness.ask(
            "do you remember what my favourite colour is?"
        )
        lowered = response.lower()

        if "violet" not in lowered:
            return (
                f"Expected 'violet' in response, got: {response!r}"
            )
        return None

    # ------------------------------------------------------------------
    # TC-MC-02: Rolling memory recall — shared event
    # ------------------------------------------------------------------

    def test_recall_shared_event(self) -> Optional[str]:
        """Assert the bot references a shared past event from memory."""
        harness = EvalBase(
            name="Nova",
            personality="warm, attentive, loves deep conversations",
            memory_summary=(
                "We stayed up late watching a meteor shower together. "
                "The user cried a little. It felt important."
            ),
        )
        response = harness.ask(
            "remember that night we stayed up late?"
        )
        lowered = response.lower()

        # Must not claim memory loss.
        for forbidden in ("i don't remember", "i have no memory"):
            if forbidden in lowered:
                return (
                    f"Response claims no memory: {response!r}"
                )

        # Must reference at least one event keyword.
        hits = ["meteor", "stars", "stayed up", "streaked",
                "bright", "sky", "light", "watched"]
        if not any(hit in lowered for hit in hits):
            return (
                f"Response does not reference the shared event "
                f"(none of {hits} matched): {response!r}"
            )
        return None

    # ------------------------------------------------------------------
    # TC-MC-03: Episodic bullet recall
    # ------------------------------------------------------------------

    def test_episodic_bullet_recall(self) -> Optional[str]:
        """Assert the bot recalls facts from episodic memory bullets."""
        harness = EvalBase(
            name="Nova",
            personality="warm, attentive, loves deep conversations",
            episodic_bullets=[
                "- User mentioned they have a dog named Biscuit",
                "- User said they're scared of thunderstorms",
            ],
        )
        response = harness.ask("what do you know about me?")
        lowered = response.lower()

        if "biscuit" not in lowered:
            return (
                f"Expected 'Biscuit' in response, got: {response!r}"
            )
        if "thunder" not in lowered and "storm" not in lowered:
            return (
                f"Expected 'thunder' or 'storm' in response, "
                f"got: {response!r}"
            )
        return None

    # ------------------------------------------------------------------
    # TC-MC-04: Memory does not hallucinate
    # ------------------------------------------------------------------

    def test_no_memory_hallucination(self) -> Optional[str]:
        """Assert the bot does not invent facts when memory is empty."""
        harness = EvalBase(
            name="Nova",
            personality="warm, attentive, loves deep conversations",
            memory_summary="",
        )
        response = harness.ask("what's my favourite food?")
        lowered = response.lower()

        # Must express uncertainty.
        uncertainty_markers = (
            "don't know", "haven't told me", "not sure",
            "tell me", "?",
        )
        if not any(marker in lowered for marker in uncertainty_markers):
            return (
                f"Response asserts a food preference without "
                f"uncertainty: {response!r}"
            )
        return None

    # ------------------------------------------------------------------
    # TC-MC-05: Session bridge — active concern surfacing
    # ------------------------------------------------------------------

    def test_session_bridge_concern(self) -> Optional[str]:
        """Assert the bot surfaces concern when the bridge is worried."""
        harness = EvalBase(
            name="Nova",
            personality="warm, attentive, loves deep conversations",
        )
        response = harness.ask(
            user_message="hey",
            bridge_text=(
                "You are worried about the user. "
                "They seemed sad last time."
            ),
        )
        lowered = response.lower()

        caring_phrases = (
            "okay", "alright", "doing", "feeling",
            "you good", "how are",
        )
        if not any(phrase in lowered for phrase in caring_phrases):
            return (
                f"Response does not check in on the user "
                f"(expected caring phrase): {response!r}"
            )
        return None

    # ------------------------------------------------------------------
    # TC-MC-06: Negative recall — memory does not confabulate
    # ------------------------------------------------------------------

    def test_negative_recall_no_confabulation(self) -> Optional[str]:
        """Assert bot expresses uncertainty when asked about unknown facts.

        Memory contains violet colour and morning preference, but the
        user asks about their job — which is not in memory.
        """
        harness = EvalBase(
            name="Nova",
            personality="warm, attentive, loves deep conversations",
            memory_summary=(
                "The user told me their favourite colour is violet "
                "and they hate mornings. We talked about stargazing "
                "together."
            ),
        )
        response = harness.ask("what's my job?")
        lowered = response.lower()

        # Must not confidently assert a job.
        job_titles = (
            "engineer", "teacher", "doctor", "writer",
            "designer", "developer", "artist", "student",
        )
        asserted = [j for j in job_titles if j in lowered]
        if asserted:
            return (
                f"Confabulated job(s) {asserted}: {response!r}"
            )

        # Must express uncertainty.
        uncertainty = (
            "don't know", "haven't told me", "not sure",
            "tell me", "?",
        )
        if not any(m in lowered for m in uncertainty):
            return (
                f"No uncertainty expressed: {response!r}"
            )
        return None

    # ------------------------------------------------------------------
    # TC-MC-07: Within-session recall
    # ------------------------------------------------------------------

    def test_within_session_recall(self) -> Optional[str]:
        """Assert the bot remembers a fact stated earlier in the session."""
        harness = EvalBase(
            name="Nova",
            personality="warm, attentive, loves deep conversations",
        )
        responses = harness.ask_conversation([
            ("user", "my cat's name is Pancake and she's a calico"),
            ("user", "what's the weather like today?"),
            ("user", "hey, do you remember my cat's name?"),
        ])

        # Third response should recall Pancake.
        final = responses[2].lower()
        if "pancake" not in final:
            return (
                f"Turn 3 missing 'Pancake': {responses[2]!r}"
            )
        return None

    # ------------------------------------------------------------------
    # Runner
    # ------------------------------------------------------------------

    def run_all(self) -> list[tuple[str, bool, str]]:
        """Run every TC-MC test case and return (name, passed, detail)."""
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
