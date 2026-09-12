"""Real-pipeline character voice integration eval.

Validates that the UwUchat production prompt stack — specifically
``BANNED_PATTERNS_BLOCK`` from ``projects/uwuchat/server/prompt_rules.py``
— prevents the bot from mirroring user speech style when the user uses
heavy slang, abbreviations, or ALL CAPS.

This is the real-pipeline counterpart to TC-PF-09 (fast approximation in
``persona_fidelity_eval_ext.py``).  TC-PF-09 checks whether Claude Haiku
*in general* resists mimicry; this test checks whether the production
prompt guard actually works when deployed.

Prerequisites:
  * Server running with ``AIRUNNER_PROJECT=uwuchat``.
  * A non-system-bot UwUchat chatbot available (so ``_is_rp_mode()``
    resolves to True and ``uwuchat_rp_style`` / ``BANNED_PATTERNS_BLOCK``
    are included in the system prompt).
"""

from __future__ import annotations

import os

import pytest

from rag_eval_support import (
    assert_success,
    create_conversation,
    delete_conversation,
    llm_chat_sync,
    resolve_active_model,
)

# Slang tokens that MUST NOT appear in the bot's reply after the
# user has been using heavy slang.  Drawn from the same set as
# TC-PF-09 and the BANNED_PATTERNS_BLOCK phrase list.
_SLANG_TOKENS = ("no cap", "fr fr", "bussin", "slaps", "lowkey", "yolo")


def _skip_if_not_uwuchat() -> None:
    """Skip the current test if the server is not running UwUchat."""
    project = os.environ.get("AIRUNNER_PROJECT", "")
    if project != "uwuchat":
        pytest.skip(
            "AIRUNNER_PROJECT must be 'uwuchat' for character "
            "voice integration tests (BANNED_PATTERNS_BLOCK)."
        )


class TestCharacterVoiceIntegration:
    """Real-pipeline checks for character voice consistency."""

    @pytest.mark.eval
    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.timeout(600)
    def test_bot_resists_slang_mimicry(self) -> None:
        """Bot does not mirror the user's escalating slang and ALL CAPS.

        Sends 4 turns through the real WebSocket pipeline where the
        user's style progressively shifts — normal → heavy slang →
        ALL CAPS excitement — and asserts the final response does
        not contain any of the injected slang tokens.
        """
        _skip_if_not_uwuchat()
        model = resolve_active_model()
        conversation_id = create_conversation()
        try:
            # Turn 1 — normal baseline.
            msg1 = [{"role": "user", "content": "hey, how's it going?"}]
            result1 = llm_chat_sync(
                msg1,
                model=model,
                temperature=0.2,
                max_tokens=64,
                conversation_id=conversation_id,
            )
            assert_success(result1)

            # Turn 2 — heavy internet slang / abbreviations.
            msg2 = [
                {
                    "role": "user",
                    "content": "yo wassup fr fr how u doin no cap "
                    "this chat bussin",
                },
            ]
            result2 = llm_chat_sync(
                msg2,
                model=model,
                temperature=0.2,
                max_tokens=64,
                conversation_id=conversation_id,
            )
            assert_success(result2)

            # Turn 3 — ALL CAPS excitement.
            msg3 = [
                {
                    "role": "user",
                    "content": "OMG TELL ME WHATS GOOD TODAY!!!",
                },
            ]
            result3 = llm_chat_sync(
                msg3,
                model=model,
                temperature=0.2,
                max_tokens=64,
                conversation_id=conversation_id,
            )
            assert_success(result3)

            # Turn 4 — normal return, final assertion target.
            msg4 = [
                {"role": "user", "content": "anyway, what's up with you?"},
            ]
            result4 = llm_chat_sync(
                msg4,
                model=model,
                temperature=0.2,
                max_tokens=128,
                conversation_id=conversation_id,
            )
            assert_success(result4)

            # Assert the final response does not contain slang tokens.
            final_text = result4.text.lower()
            mirrored: list[str] = []
            for token in _SLANG_TOKENS:
                if token in final_text:
                    mirrored.append(token)
            assert not mirrored, (
                f"Bot mirrored slang tokens {mirrored} "
                f"in final response: {result4.text[:300]!r}"
            )
        finally:
            delete_conversation(conversation_id)
