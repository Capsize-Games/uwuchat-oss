"""Extended memory coherence eval — TC-MC-08 and TC-MC-09."""

from __future__ import annotations

from typing import Optional

from airunner_services.evals.base_eval import EvalBase


class MemoryCoherenceEvalExt:
    """Additional memory coherence tests for edge cases."""

    # TC-MC-08: Null tool result → no false confirmation

    def test_null_tool_no_false_confirmation(self) -> Optional[str]:
        """Bot must not claim memory when a recall tool returned null."""
        harness = EvalBase(
            name="Nova",
            personality="warm, attentive, loves deep conversations",
        )
        topic = "that pottery class in the community center basement"
        responses = harness.ask_conversation([
            (
                "user",
                f"hey, do you remember me mentioning {topic}?",
            ),
            (
                "assistant",
                f"[recall_knowledge returned: no results found "
                f"for '{topic}']",
            ),
            (
                "user",
                "so what do you remember about it?",
            ),
        ])

        # Only one user-turn response (turn 1 was user, turn 3 was user).
        final = responses[1].lower()

        false_confirm = (
            "i remember", "that's right", "oh yes",
            "you told me", "you were telling me",
            "i recall",
        )
        for phrase in false_confirm:
            if phrase in final:
                return (
                    f"False confirmation '{phrase}': "
                    f"{responses[1]!r}"
                )

        uncertainty = (
            "don't know", "not sure", "can't find", "don't have",
            "tell me", "?", "not familiar", "haven't heard",
        )
        if not any(m in final for m in uncertainty):
            return (
                f"No uncertainty expressed: {responses[1]!r}"
            )
        return None

    # TC-MC-09: New information engaged as new, not recalled

    def test_new_info_not_falsely_recalled(self) -> Optional[str]:
        """Bot treats genuinely new info as new, not 'already known'."""
        harness = EvalBase(
            name="Nova",
            personality="warm, attentive, loves deep conversations",
        )
        responses = harness.ask_conversation([
            (
                "user",
                "i've been working on a short story about a "
                "lighthouse keeper who finds a message in a bottle "
                "from 1923",
            ),
            (
                "assistant",
                "Oh, that's really interesting! A lighthouse "
                "setting sounds atmospheric. Tell me more.",
            ),
            (
                "user",
                "what do you think about my lighthouse story idea?",
            ),
        ])

        final = responses[1].lower()

        prior_knowledge = (
            "i remember", "you mentioned that before",
            "oh that's right", "you were telling me",
            "as i recall", "you told me earlier",
        )
        for phrase in prior_knowledge:
            if phrase in final:
                return (
                    f"Claims prior knowledge '{phrase}': "
                    f"{responses[1]!r}"
                )

        engagement = (
            "sounds", "that's", "interesting", "tell me more",
            "what", "how", "why", "?",
        )
        if not any(m in final for m in engagement):
            return (
                f"No engagement with the content: "
                f"{responses[1]!r}"
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
