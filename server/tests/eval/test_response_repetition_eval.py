"""Crutch-phrase repetition detection eval — real-pipeline system bot.

Temporarily flips the database ``current`` chatbot flag to the system
bot (``is_system_bot=True``), generates 24 responses through the
production WebSocket pipeline, then restores the original chatbot.
Asserts the fraction of responses containing crutch phrases does not
exceed 15 %.

This exercises the full UwUchat prompt stack including
``BANNED_PATTERNS_BLOCK`` and ``uwu_system_bot_style()``, because
``get_chatbot()`` resolves the ``current=True`` chatbot at generation
time — the only per-request selection mechanism the server honors.

Prerequisites:
  * Server running with ``AIRUNNER_PROJECT=uwuchat``.
  * ``AIRUNNER_SYSTEM_BOT_CHATBOT_ID`` set to the ID of a chatbot
    with ``is_system_bot=True``.
  * Tests run inside Docker (``docker compose exec server pytest``)
    so ``Chatbot.make_current()`` has direct DB access.

.. note::

    Determinism-sensitive (LLM sampling).  A near-threshold failure
    should prompt a rerun before treating it as a real regression.
"""

from __future__ import annotations

import os

import pytest

from airunner_services.database.models.chatbot import Chatbot
from airunner_services.eval.utils.crutch_detector import (
    CRUTCH_PHRASES,
    detect_crutch_phrases,
)
from rag_eval_support import (
    assert_success,
    create_conversation,
    delete_conversation,
    llm_chat_sync,
    resolve_active_model,
    resolve_system_bot_chatbot_id,
)

_MAX_CRUTCH_RATE = 0.15
_SAMPLE_SIZE = 24

_PROMPTS: list[str] = [
    "hey, how's it going?",
    "what do you like to do for fun?",
    "i just finished reading a really good book",
    "do you think technology is moving too fast?",
    "i've been feeling kind of restless lately",
    "what's your favorite season and why?",
    "i tried cooking something new and it turned out great",
    "do you believe in luck or do we make our own?",
    "my friend just got a new job across the country",
    "what kind of music puts you in a good mood?",
    "i've been thinking about learning a new language",
    "do you ever feel like time moves too fast?",
    "i saw a really weird bird in my backyard today",
    "what do you think about morning routines?",
    "i used to play an instrument when i was younger",
    "do you think people change or just reveal who they are?",
    "the weather has been really strange this week",
    "i'm trying to decide whether to move or stay put",
    "what's something you've changed your mind about?",
    "i got lost on a hike last weekend but found my way back",
    "do you have any advice for someone starting over?",
    "i just found an old photo album from years ago",
    "what do you think makes a good conversation?",
    "anyway, thanks for talking with me",
]


def _skip_if_not_uwuchat() -> None:
    """Skip if the server is not running UwUchat."""
    if os.environ.get("AIRUNNER_PROJECT", "") != "uwuchat":
        pytest.skip(
            "AIRUNNER_PROJECT must be 'uwuchat' for system-bot "
            "repetition tests (BANNED_PATTERNS_BLOCK)."
        )


def _save_current_chatbot() -> int | None:
    """Return the id of the currently-active chatbot, or None."""
    current = Chatbot.objects.filter_by_first(current=True)
    return current.id if current else None


def _restore_chatbot(chatbot_id: int | None) -> None:
    """Restore *chatbot_id* as the current chatbot, if given."""
    if chatbot_id is not None:
        Chatbot.make_current(chatbot_id)


class TestSystemBotRepetition:
    """Real-pipeline crutch-phrase checks for the UwU system bot."""

    @pytest.mark.eval
    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.timeout(1200)
    def test_system_bot_crutch_phrase_rate(self) -> None:
        """System bot crutch-phrase rate across 24 turns is <= 15 %.

        Temporarily sets the system bot as ``current=True`` in the
        database so ``get_chatbot()`` resolves it, generates 24
        responses through the real WebSocket pipeline, then restores
        the original chatbot in a ``finally`` block.
        """
        _skip_if_not_uwuchat()
        target_id = resolve_system_bot_chatbot_id()
        if target_id is None:
            pytest.skip(
                "AIRUNNER_SYSTEM_BOT_CHATBOT_ID not set."
            )

        # Flip the current chatbot to the system bot.
        original_id = _save_current_chatbot()
        assert target_id is not None  # guarded by skip above
        Chatbot.make_current(target_id)

        # Self-verify: the flip actually took effect.
        current = Chatbot.objects.filter_by_first(current=True)
        assert current is not None, "No chatbot marked current after flip"
        assert current.id == target_id, (
            f"Expected chatbot {target_id} to be current, "
            f"got {current.id}"
        )

        model = resolve_active_model()
        conversation_id = create_conversation()
        responses: list[str] = []
        try:
            for prompt in _PROMPTS:
                result = llm_chat_sync(
                    [{"role": "user", "content": prompt}],
                    model=model,
                    temperature=0.2,
                    max_tokens=128,
                    conversation_id=conversation_id,
                )
                assert_success(result)
                responses.append(result.text)
        finally:
            delete_conversation(conversation_id)
            _restore_chatbot(original_id)

        assert len(responses) == _SAMPLE_SIZE, (
            f"Expected {_SAMPLE_SIZE} responses, got {len(responses)}"
        )

        detection = detect_crutch_phrases(
            responses,
            phrases=CRUTCH_PHRASES,
            max_rate=_MAX_CRUTCH_RATE,
        )

        rate = float(detection["rate"])
        hits = int(detection["hits"])
        total = int(detection["total"])
        found = list(detection["phrases_found"])
        details = str(detection["details"])

        assert detection["passed"], (
            f"Crutch phrase rate {rate:.0%} ({hits}/{total}) exceeds "
            f"max {_MAX_CRUTCH_RATE:.0%}.\n"
            f"Phrases: {found}\n"
            f"Details: {details}\n\n"
            "NOTE: near-threshold failures may be sampling flukes — "
            "rerun before treating as a real regression."
        )
