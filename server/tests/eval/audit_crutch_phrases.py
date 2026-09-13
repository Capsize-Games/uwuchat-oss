"""Audit crutch-phrase frequency before/after prompt changes (Step 1).

Generates 24 responses from each bot type, scans for crutch phrases,
and reports the frequency per bot type.  Run inside Docker::

    docker compose exec server python \\
        server/tests/eval/audit_crutch_phrases.py

For the system-bot audit this temporarily flips the database
``current`` chatbot flag to the system bot, generates responses
through the production WebSocket pipeline, then restores the
original chatbot — the same mechanism ``get_chatbot()`` uses.

Prerequisites for system-bot audit:
  * ``AIRUNNER_PROJECT=uwuchat``
  * ``AIRUNNER_SYSTEM_BOT_CHATBOT_ID`` set to a chatbot with
    ``is_system_bot=True``
  * Script runs inside Docker (has direct DB access)
"""

from __future__ import annotations

import os
import sys

from airunner_services.database.models.chatbot import Chatbot
from airunner_services.eval.utils.crutch_detector import (
    CRUTCH_PHRASES,
    detect_crutch_phrases,
)
from airunner_services.evals.base_eval import EvalBase

# ── RP character audit (EvalBase — standalone, no server needed) ──────────

_RP_PROMPTS: list[str] = [
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
    "i got lost on a hike but found my way back",
    "do you have any advice for someone starting over?",
    "i just found an old photo album from years ago",
    "what do you think makes a good conversation?",
    "anyway, thanks for talking with me",
]


def _audit_rp_character(
    name: str, personality: str, speech: str,
) -> dict[str, object]:
    """Audit one RP character for crutch phrase frequency."""
    harness = EvalBase(
        name=name, personality=personality, speech_patterns=speech,
    )
    responses = [harness.ask(prompt) for prompt in _RP_PROMPTS]
    return detect_crutch_phrases(responses, phrases=CRUTCH_PHRASES)


def run_rp_audit() -> None:
    """Run crutch-phrase audit against 3 RP characters."""
    characters = [
        (
            "Luna", "shy, gentle, loves stars",
            "speaks tentatively, uses ellipses, never formal",
        ),
        (
            "Blaze", "brash, loud, cocky, impulsive",
            "short punchy sentences, uses yeah and nah",
        ),
        (
            "Mochi", "sweet, timid, avoids conflict",
            "soft-spoken, hesitant, uses um and maybe",
        ),
    ]
    print("\n── RP Character Crutch-Phrase Audit ──")
    for name, personality, speech in characters:
        result = _audit_rp_character(name, personality, speech)
        rate = float(result["rate"])
        hits = int(result["hits"])
        total = int(result["total"])
        print(
            f"  {name:10s}  {hits}/{total}  "
            f"({rate:.0%})  {'PASS' if result['passed'] else 'FAIL'}"
        )
    print()


# ── System-bot audit (real pipeline — requires running server) ────────────

def _can_audit_system_bot() -> bool:
    """Return True when the system-bot audit prerequisites are met."""
    if os.environ.get("AIRUNNER_PROJECT", "") != "uwuchat":
        return False
    return bool(os.environ.get("AIRUNNER_SYSTEM_BOT_CHATBOT_ID", ""))


def _resolve_system_bot_id() -> int | None:
    """Return the system-bot chatbot ID from env, or None."""
    raw = os.environ.get("AIRUNNER_SYSTEM_BOT_CHATBOT_ID", "")
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def run_system_bot_audit() -> None:
    """Run crutch-phrase audit against the system bot via real pipeline.

    Temporarily flips the DB ``current`` flag to the system bot,
    generates responses through the production WebSocket pipeline,
    then restores the original chatbot.
    """
    if not _can_audit_system_bot():
        print(
            "── System-Bot Crutch-Phrase Audit ──\n"
            "  SKIPPED — set AIRUNNER_PROJECT=uwuchat and "
            "AIRUNNER_SYSTEM_BOT_CHATBOT_ID\n"
        )
        return

    target_id = _resolve_system_bot_id()
    if target_id is None:
        print(
            "── System-Bot Crutch-Phrase Audit ──\n"
            "  SKIPPED — AIRUNNER_SYSTEM_BOT_CHATBOT_ID not an int\n"
        )
        return

    from rag_eval_support import (
        assert_success,
        create_conversation,
        delete_conversation,
        llm_chat_sync,
        resolve_active_model,
    )

    # Save and flip the current chatbot.
    original = Chatbot.objects.filter_by_first(current=True)
    original_id = original.id if original else None
    Chatbot.make_current(target_id)

    # Self-verify.
    current = Chatbot.objects.filter_by_first(current=True)
    if current is None or current.id != target_id:
        if original_id is not None:
            Chatbot.make_current(original_id)
        print(
            "── System-Bot Crutch-Phrase Audit ──\n"
            f"  ERROR — flip to chatbot {target_id} failed.\n"
        )
        return

    model = resolve_active_model()
    conversation_id = create_conversation()
    responses: list[str] = []
    try:
        for prompt in _RP_PROMPTS:
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
        if original_id is not None:
            Chatbot.make_current(original_id)

    detection = detect_crutch_phrases(
        responses, phrases=CRUTCH_PHRASES,
    )
    rate = float(detection["rate"])
    hits = int(detection["hits"])
    total = int(detection["total"])
    print(
        "── System-Bot Crutch-Phrase Audit ──\n"
        f"  System Bot  {hits}/{total}  "
        f"({rate:.0%})  {'PASS' if detection['passed'] else 'FAIL'}\n"
    )


# ── Main ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    run_rp_audit()
    run_system_bot_audit()
    sys.exit(0)
