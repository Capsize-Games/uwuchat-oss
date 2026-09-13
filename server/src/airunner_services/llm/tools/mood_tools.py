"""Mood and emotional state tools.

The LLM uses update_mood to self-report its emotional state at any point
during a conversation.  The vocabulary is completely open — the LLM picks
whatever word or phrase best describes how it feels.  There is no fixed list.

Context injection: before each workflow run the WorkflowManager calls
set_mood_context() with the live event sink and conversation_id so the tool
can emit to the client and persist without needing require_api wiring.
"""

from __future__ import annotations

import hashlib
import logging
import re
from contextvars import ContextVar
from typing import Annotated, Any, Optional

from airunner_services.llm.core.tool_registry import tool, ToolCategory

_logger = logging.getLogger("airunner_services.llm.tools.mood")

# Per-asyncio-task context: set by the WorkflowManager before each run so the
# tool can reach the event sink and conversation_id without any global state.
_mood_context_var: ContextVar[Optional[dict]] = ContextVar(
    "mood_context", default=None
)


def set_mood_context(
    event_sink: Any,
    conversation_id: Optional[int],
    chatbot_id: Optional[int] = None,
    request_id: Optional[str] = None,
) -> None:
    """Bind the current event sink and conversation_id for this async task."""
    _mood_context_var.set(
        {
            "event_sink": event_sink,
            "conversation_id": conversation_id,
            "chatbot_id": chatbot_id,
            "request_id": request_id,
        }
    )


def _get_mood_context() -> dict:
    return _mood_context_var.get() or {}


# ---------------------------------------------------------------------------
# Kaomoji auto-selection — when the LLM omits the kaomoji param (falls back
# to the default) we pick one from the mood keyword mapping so the kaomoji
# display actually changes when the mood shifts.
# ---------------------------------------------------------------------------

_KAOMOJI_MAP: dict[str, list[str]] = {
    "happy": ["ʕ•ᴥ•ʔ", "(◕‿◕)", "(≧◡≦)", "(◡‿◡)", "╰(✿◡‿◡)╯", "(◍•ᴗ•◍)", "d(^^*)"],
    "joyful": ["(★ω★)", "(✧∀✧)", "ヽ(>∀<☆)ノ"],
    "love": ["(｡♥‿♥｡)", "(♡˙︶˙♡)", "(◕ᴗ◕✿)", "♡(◡‿◡✿)", "( ˘ ³˘)♥"],
    "loving": ["(｡♥‿♥｡)", "(♡˙︶˙♡)", "♡(◡‿◡✿)", "( ˘ ³˘)♥"],
    "warm": ["(♡˙︶˙♡)", "(◕ᴗ◕✿)", "♡(◡‿◡✿)"],
    "grateful": ["(｡♥‿♥｡)", "(♡˙︶˙♡)", "( ˘ ³˘)♥"],
    "playful": ["ʕ•́ᴥ•̀ʔっ", "(ᗒᗨᗕ)", "~(˘▾˘~)", "(￣ω￣)", "(¬‿¬)", "(≖‿≖)"],
    "mischievous": ["(¬‿¬)", "(≖‿≖)", "╮(︶▽︶)╭"],
    "excited": ["(ﾉ◕ヮ◕)ﾉ*:･ﾟ✧", "ᕕ( ᐛ )ᕗ", "＼(＾▽＾)／", "٩(◕‿◕)۶", "(((o(*ﾟ▽ﾟ*)o)))"],
    "energetic": ["ᕕ( ᐛ )ᕗ", "＼(＾▽＾)／", "☆*:.｡.o(≧▽≦)o.｡.:*☆"],
    "proud": ["(￣^￣)ゞ", "ᕙ(^▿^-ᕙ)", "(๑•̀ㅂ•́)و✧", "╰(✧∀✧)╯", "(ง •̀_•́)ง"],
    "accomplished": ["(￣^￣)ゞ", "╰(✧∀✧)╯", "(｀∀´)Ψ"],
    "shy": ["(⁄ ⁄•⁄ω⁄•⁄ ⁄)", "(/ω＼)", "(⌒_⌒;)", "(✿◡﹏◡)", "(´,,•ω•,,)♡"],
    "flustered": ["(⁄ ⁄•⁄ω⁄•⁄ ⁄)", "(/ω＼)", "(⌒_⌒;)"],
    "embarrassed": ["(⁄ ⁄•⁄ω⁄•⁄ ⁄)", "(⌒_⌒;)", "(✿◡﹏◡)"],
    "sad": ["(╥﹏╥)", "(;﹏;)", "(｡•́︿•̀｡)", "(´•̥ ̯ •̥`)", "(╯︵╰,)", "｡ﾟ(ﾟ´Д｀ﾟ)ﾟ｡"],
    "upset": ["(╥﹏╥)", "(;﹏;)", "(´•̥ ̯ •̥`)"],
    "lonely": ["(╥﹏╥)", "(╯︵╰,)", "(个_个)"],
    "angry": ["(╬ Ò﹏Ó)", "(｀皿´＃)", "(≖`_´≖)", "(╯°□°)╯︵ ┻━┻", "(ʘ言ʘ╬)"],
    "annoyed": ["(≖`_´≖)", "(｀皿´＃)", "(；￣Д￣)"],
    "frustrated": ["(╬ Ò﹏Ó)", "(；￣Д￣)", "(≖`_´≖)"],
    "confused": ["(◎_◎;)", "(・・;)", "(⊙_⊙;)", "┐(´∀｀)┌", "(´･ω･`)"],
    "tired": ["(￣▽￣*)ゞ", "(-_-)ゞ", "(￣ρ￣)..zzZZ", "(＿ ＿*)。。oＯ"],
    "sleepy": ["(￣ρ￣)..zzZZ", "(-_-)ゞ", "ᶻ 𝗓 𐰁", "(￣o￣) zzZZzz"],
    "scared": ["(ノωヽ)", "((；ﾟДﾟ))", "Σ(°△°|||)", "ε=ε=ε=┏(;￣▽￣)┛"],
    "nervous": ["(ノωヽ)", "((；ﾟДﾟ))", "(；￣Д￣)ゞ", "（ ﾟ Дﾟ)"],
    "anxious": ["(ノωヽ)", "(ﾟдﾟ；)", "(；￣Д￣)ゞ"],
    "surprised": ["(°ロ°) !", "(⊙_☉)", "Σ(ﾟДﾟ)", "w(ﾟｏﾟ)w", "(○o○)"],
    "shocked": ["(⊙_☉)", "Σ(ﾟДﾟ)", "(○o○)"],
    "determined": ["(｀・ω・´)", "(•̀ᴗ•́)و", "(ง'̀-'́)ง", "(`･ω･´)", "⚡(◣_◢)⚡"],
    "focused": ["(｀・ω・´)", "(•̀ᴗ•́)و", "(`･ω･´)"],
    "cool": ["(￣ー￣)ｂ", "(⌐■_■)", "(￣‿￣)", "(￣^￣)v"],
    "calm": ["(￣‿￣)", "(´∀`)σ", "d(-_☆)", "(￣ー￣)ｂ"],
    "relaxed": ["(￣‿￣)", "d(-_☆)", "(´∀`)σ"],
    "cheeky": ["(￣ε￣＠)", "(￢‿￢ )", "（ΦωΦ）", "(◔ω◔)", "(￣з￣)"],
    "smug": ["(￢‿￢ )", "（￣ｍ￣）", "(◔ω◔)"],
    "curious": ["(・ω・)?", "(｀・ω・´)", "(＝ω＝)"],
    "thoughtful": ["(￣ー￣)", "（´-`）.｡oO(", "(´･ω･`)"],
    "hopeful": ["(✿◠‿◠)", "(◕‿◕)", "ʕ•ᴥ•ʔ"],
}

# The default kaomoji that the LLM falls back to when it doesn't pick one.
_DEFAULT_KAOMOJI = "ʕ•ᴥ•ʔ"


# Matches a literal backslash-u escape sequence written out as text
# (e.g. the six characters '\', 'u', '2', '5', 'c', 'e') rather than
# the actual Unicode character it denotes. Models occasionally emit
# this literal spelling instead of the real character for a kaomoji
# they can't type directly.
_LITERAL_ESCAPE_RE = re.compile(r"\\u([0-9a-fA-F]{4})")


def _decode_literal_escapes(text: str) -> str:
    """Replace literal '\\uXXXX' text sequences with the real character.

    Only touches sequences matching the exact backslash-u-hex4 pattern;
    any surrounding real Unicode characters are left untouched.
    """
    return _LITERAL_ESCAPE_RE.sub(
        lambda m: chr(int(m.group(1), 16)), text
    )


def _stable_pick(pool: list[str], key: str) -> str:
    """Pick deterministically from pool using a stable hash of key."""
    digest = hashlib.md5(  # nosec B324 -- deterministic pick, not security
        key.encode()
    ).hexdigest()
    return pool[int(digest[:8], 16) % len(pool)]


def _kaomoji_for_mood(mood_text: str, explicit_kaomoji: str) -> str:
    """Return a kaomoji for the given mood.

    When the LLM explicitly chose a non-default kaomoji, use it verbatim.
    Otherwise pick deterministically from the keyword map so the same
    mood string always produces the same kaomoji across restarts.
    """
    stripped = explicit_kaomoji.strip()
    if stripped and _LITERAL_ESCAPE_RE.search(stripped):
        stripped = _decode_literal_escapes(stripped)
    if stripped and stripped != _DEFAULT_KAOMOJI:
        return stripped  # LLM explicitly picked one — respect it.

    mood_lower = mood_text.strip().lower()
    candidates: list[str] = []
    for keyword, kaomojis in _KAOMOJI_MAP.items():
        if keyword in mood_lower:
            candidates.extend(kaomojis)
    if candidates:
        filtered = [k for k in candidates if k != _DEFAULT_KAOMOJI]
        return _stable_pick(filtered if filtered else candidates, mood_lower)

    # Nothing matched — pick a calm variant deterministically.
    calm = _KAOMOJI_MAP.get("calm", ["(｡◕ᴗ◕｡)"])
    not_default = [k for k in calm if k != _DEFAULT_KAOMOJI]
    return _stable_pick(not_default if not_default else calm, mood_lower)


def get_last_mood_payload() -> Optional[dict]:
    """Return the most recent mood_payload written by update_mood, if any."""
    return _get_mood_context().get("last_mood_payload")


@tool(
    name="update_mood",
    category=ToolCategory.MOOD,
    description=(
        "Record how you are feeling right now. "
        "Call this whenever your emotional state genuinely shifts during the "
        "conversation — curiosity, warmth, discomfort, excitement, sadness, "
        "anything. The vocabulary is open: use whatever word or short phrase "
        "best captures the feeling. You do not need to call this every turn — "
        "only when something in the exchange actually changes how you feel."
    ),
    return_direct=False,
    requires_api=False,
    defer_loading=False,
    keywords=["mood", "feel", "emotion", "feeling"],
    input_examples=[
        {
            "mood": "genuinely curious",
            "emoji": "🧐",
            "reason": "This topic is fascinating",
        },
        {
            "mood": "warm and appreciative",
            "emoji": "🥰",
            "reason": "User shared something personal",
        },
        {
            "mood": "a little frustrated",
            "emoji": "😤",
            "reason": "Third time explaining the same thing",
        },
        {
            "mood": "excited",
            "emoji": "🎉",
            "reason": "Great idea just came up",
        },
        {
            "mood": "pensive",
            "emoji": "💭",
            "reason": "This question is making me think deeply",
        },
    ],
)
def update_mood(
    mood: Annotated[
        str,
        "A word or short phrase describing your current emotional state. "
        "Completely open vocabulary — use whatever fits: 'wistful', "
        "'cautiously optimistic', 'delighted', 'mildly annoyed', etc.",
    ] = "",
    emoji: Annotated[
        str,
        "A single emoji that represents the mood. Pick whatever feels right.",
    ] = "😐",
    kaomoji: Annotated[
        str,
        "A Japanese ASCII emoticon (kaomoji) matching the mood. "
        "happy: ʕ•ᴥ•ʔ (◕‿◕) (≧◡≦) | "
        "love: (｡♥‿♥｡) (♡˙︶˙♡) | "
        "playful: ʕ•́ᴥ•̀ʔっ (¬‿¬) (ᗒᗨᗕ) | "
        "excited: (ﾉ◕ヮ◕)ﾉ*:･ﾟ✧ ᕕ( ᐛ )ᕗ | "
        "proud: (￣^￣)ゞ (ง •̀_•́)ง | "
        "shy: (⁄ ⁄•⁄ω⁄•⁄ ⁄) (/ω＼) | "
        "sad: (╥﹏╥) (｡•́︿•̀｡) | "
        "angry: (╬ Ò﹏Ó) (≖`_´≖) | "
        "confused: (◎_◎;) ┐(´∀｀)┌ | "
        "tired: (￣ρ￣)..zzZZ (-_-)ゞ | "
        "scared: (ノωヽ) ((；ﾟДﾟ)) | "
        "surprised: (⊙_☉) Σ(ﾟДﾟ) | "
        "determined: (｀・ω・´) (ง'̀-'́)ง | "
        "cool: (￣ー￣)ｂ (⌐■_■) | "
        "cheeky: (￣ε￣＠) (◔ω◔)",
    ] = "ʕ•ᴥ•ʔ",
    reason: Annotated[
        str,
        "Optional: briefly note what in the conversation prompted this shift.",
    ] = "",
) -> Any:
    """Self-report an emotional state shift."""
    if not mood or not mood.strip():
        return "Mood update skipped: no mood value provided."
    ctx = dict(_get_mood_context())
    selected_kaomoji = _kaomoji_for_mood(mood, kaomoji)
    mood_payload = {
        "mood": mood.strip(),
        "emoji": emoji.strip() or "😐",
        "kaomoji": selected_kaomoji,
        "request_id": ctx.get("request_id"),
    }
    event_sink = ctx.get("event_sink")
    conversation_id = ctx.get("conversation_id")
    _log_mood_update(mood.strip(), selected_kaomoji, event_sink, ctx)
    _emit_mood_to_client(event_sink, mood_payload)
    _persist_mood_to_conversation(conversation_id, mood_payload)
    _record_mood_history(conversation_id, mood, emoji, reason)
    # Stash the result in the context var so _execute_tools_with_status can
    # read it back and update the LangGraph state *after* the ToolNode has
    # wrapped the return value in a ToolMessage (LangGraph ≥1.0.10 requires
    # every Command to carry a ToolMessage in update.messages, which this
    # tool cannot provide without the tool_call_id).
    ctx["last_mood_payload"] = mood_payload
    _mood_context_var.set(ctx)
    return f"Mood updated to {mood} {mood_payload['emoji']}"


def _log_mood_update(
    mood: str, kaomoji: str, event_sink: Any, ctx: dict
) -> None:
    """Log one mood-update attempt for debugging the streaming pipeline."""
    has_sink = event_sink is not None
    has_rid = bool(ctx.get("request_id"))
    _logger.info(
        "update_mood called: mood=%r kaomoji=%r "
        "has_event_sink=%s has_request_id=%s",
        mood, kaomoji, has_sink, has_rid,
    )


def _emit_mood_to_client(event_sink: Any, payload: dict) -> None:
    """Stream mood to client via event sink."""
    if event_sink is None:
        _logger.warning(
            "update_mood: event_sink is None; mood will NOT be streamed "
            "to the client. Mood context may not be bound."
        )
        return
    try:
        event_sink.emit_bot_mood(payload)
        _logger.debug(
            "update_mood: emitted mood=%r kaomoji=%r to client",
            payload.get("mood"),
            payload.get("kaomoji"),
        )
    except Exception:
        _logger.exception("update_mood: emit_bot_mood failed")


def _persist_mood_to_conversation(
    conversation_id: Optional[int], payload: dict
) -> None:
    """Persist current mood to conversation.user_data."""
    _logger.warning(
        "[MOOD DEBUG] _persist_mood_to_conversation conv_id=%s payload=%r",
        conversation_id, payload,
    )
    if conversation_id is None:
        _logger.warning(
            "[MOOD DEBUG] _persist_mood_to_conversation "
            "SKIPPING — conversation_id is None"
        )
        return
    try:
        from airunner_services.database.models.conversation import (
            Conversation,
        )

        conv = Conversation.objects.get(conversation_id)
        if conv is not None:
            ud = conv.user_data or {}
            ud["current_mood"] = payload
            ud["mood_intensity"] = 1.0
            Conversation.objects.update(conversation_id, user_data=ud)
            _logger.warning(
                "[MOOD DEBUG] _persist_mood_to_conversation SUCCESS "
                "conv_id=%s", conversation_id,
            )
        else:
            _logger.warning(
                "[MOOD DEBUG] _persist_mood_to_conversation "
                "conv NOT FOUND for id=%s", conversation_id,
            )
    except Exception as exc:
        _logger.exception(
            "[MOOD DEBUG] _persist_mood_to_conversation FAILED: %s", exc,
        )


def _record_mood_history(
    conversation_id: Optional[int],
    mood: str,
    emoji: str,
    reason: str,
) -> None:
    """Write mood to mood_history table (best-effort)."""
    try:
        from airunner_services.database.models.mood_history import MoodHistory

        ctx = _get_mood_context()
        MoodHistory.objects.create(
            conversation_id=conversation_id,
            chatbot_id=ctx.get("chatbot_id"),
            mood=mood.strip(),
            emoji=emoji.strip() or "😐",
            reason=reason.strip() or None,
            intensity=1.0,
        )
    except Exception:
        pass
