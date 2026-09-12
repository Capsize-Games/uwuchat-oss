"""search_conversations — browse whole Conversation records by date,
session, or keyword.

Complement to recall_conversation's semantic search: instead of finding
turns similar to a query text, this tool lets the LLM browse conversation
transcripts by concrete, safe filters and get back decrypted message
content with metadata.
"""

from typing import Annotated

from airunner_services.llm.core.tool_registry import ToolCategory, tool
from airunner_services.llm.managers.prompt_builder.per_turn_temporal import (
    relative_time_ago,
)
from airunner_services.settings import AIRUNNER_LOG_LEVEL
from airunner_services.utils.application import get_logger

logger = get_logger(__name__, AIRUNNER_LOG_LEVEL)

_MAX_RESULTS_HARD_CAP = 5
_MAX_MESSAGES_PER_CONV = 10
_MSG_CHAR_LIMIT = 300


@tool(
    name="search_conversations",
    category=ToolCategory.RECALL,
    description=(
        "Search full past conversations by date, session, or keyword —"
        " not just a single similar message. Use this when the user asks"
        " what you talked about on a specific day or in a specific past"
        " session, or wants a broader browse of history rather than one"
        " matching exchange. Returns actual conversation excerpts with"
        " when they happened."
    ),
    return_direct=False,
    requires_api=False,
    defer_loading=False,
    keywords=[
        "yesterday", "today", "last week", "this morning",
        "what did we talk about", "last time we talked",
        "our last conversation",
    ],
    input_examples=[
        {"when": "yesterday"},
        {"keyword": "the dentist appointment"},
        {"when": "last monday", "keyword": "stats homework"},
    ],
)
def search_conversations(
    when: Annotated[
        str, "Relative date phrase, e.g. 'yesterday', 'last week',"
        " 'monday'. Leave empty to search all time."
    ] = "",
    keyword: Annotated[
        str, "Text to look for in the conversation. Leave empty to"
        " just browse by date/session."
    ] = "",
    session_id: Annotated[
        int, "Specific session id if known (from a prior tool result)."
        " Leave 0 for unset."
    ] = 0,
    max_results: Annotated[
        int, "Maximum conversations to return (server caps this)."
    ] = 3,
) -> str:
    """Search past conversations by date, session, or keyword."""
    try:
        from airunner_services.knowledge_context import (
            get_knowledge_chatbot_id,
        )

        chatbot_id = get_knowledge_chatbot_id()
        if not chatbot_id:
            return "No chatbot context available."

        scope = _resolve_scope(chatbot_id)
        session_ids = _resolve_session_ids_for_when(
            when, scope, chatbot_id
        )
        if when and session_ids is not None and not session_ids:
            return f"No conversations found for '{when}'."

        convs = _fetch_conversations(
            scope, session_ids, session_id, max_results
        )
        if not convs:
            if when:
                return f"No conversations found for '{when}'."
            return "No past conversations found."

        omnipotent = _is_omnipotent()
        blocks = _format_conversation_blocks(
            convs, keyword, omnipotent
        )
        if not blocks:
            msg = f"No conversations matching '{keyword}' found."
            if when:
                msg += f" (date filter: {when})"
            return msg

        return "\n\n".join(blocks)
    except Exception as exc:
        logger.error("search_conversations failed: %s", exc)
        return f"Error searching conversations: {exc}"


# ---------------------------------------------------------------------------
# Scope helpers
# ---------------------------------------------------------------------------


def _is_omnipotent() -> bool:
    """Return True when the current chatbot is the system bot with
    omnipotent_knowledge enabled."""
    try:
        from airunner_services.database.models.chatbot import Chatbot
        from airunner_services.knowledge_context import (
            get_knowledge_chatbot_id,
        )

        chatbot_id = get_knowledge_chatbot_id()
        if chatbot_id is None:
            return False
        chatbot = Chatbot.objects.get(chatbot_id)
        if chatbot is None:
            return False
        return bool(
            getattr(chatbot, "is_system_bot", False)
            and getattr(chatbot, "omnipotent_knowledge", False)
        )
    except Exception:
        return False


def _resolve_scope(chatbot_id: int) -> list[int]:
    """Return the list of chatbot IDs this search should cover."""
    if not _is_omnipotent():
        return [chatbot_id]
    try:
        from airunner_services.database.models.chatbot import Chatbot
        from airunner_services.knowledge_rag import (
            KnowledgeBaseRAGMixin,
        )

        blocked = KnowledgeBaseRAGMixin._blocked_chatbot_ids()
        all_bots = Chatbot.objects.query().all()
        return [b.id for b in all_bots if b.id not in blocked]
    except Exception:
        return [chatbot_id]


# ---------------------------------------------------------------------------
# Date/session resolution
# ---------------------------------------------------------------------------


def _resolve_session_ids_for_when(
    when: str, scope: list[int], chatbot_id: int,
) -> list[int] | None:
    """Return matching session ids for a date phrase, or None if
    ``when`` is empty/parses to no range.  An empty list means the
    range was valid but matched zero sessions."""
    if not when.strip():
        return None
    try:
        from airunner_services.database.models.chatbot import Chatbot
        from airunner_services.database.models.chat_session import (
            ChatSession,
        )
        from airunner_services.world.temporal_query import (
            parse_relative_date_range,
            resolve_reference_datetime,
        )

        chatbot = Chatbot.objects.get(chatbot_id)
        if chatbot is None:
            return None
        reference_dt = resolve_reference_datetime(chatbot)
        date_range = parse_relative_date_range(when, reference_dt)
        if date_range is None:
            return []  # when supplied but didn't parse — treat as no match
        start, end = date_range
        sessions = (
            ChatSession.objects.query()
            .filter(
                ChatSession.chatbot_id.in_(scope),
                ChatSession.last_message_at >= start,
                ChatSession.last_message_at < end,
            )
            .all()
        )
        return [s.id for s in sessions]
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Fetch + format
# ---------------------------------------------------------------------------


def _fetch_conversations(
    scope: list[int],
    session_ids: list[int] | None,
    session_id: int,
    max_results: int,
):
    """Return matching Conversation rows, ordered by id desc."""
    from airunner_services.database.models.conversation import (
        Conversation,
    )

    limit = min(max_results, _MAX_RESULTS_HARD_CAP)
    q = Conversation.objects.query().filter(
        Conversation.chatbot_id.in_(scope),
    )
    if session_ids is not None:
        q = q.filter(Conversation.session_id.in_(session_ids))
    if session_id:
        q = q.filter(Conversation.session_id == session_id)
    return q.order_by(Conversation.id.desc()).limit(limit).all()


def _format_conversation_blocks(
    convs, keyword: str, omnipotent: bool,
) -> list[str]:
    """Format each conversation as a labeled block, filtering by
    keyword if supplied.  Returns empty list if nothing matches."""
    blocks: list[str] = []
    keyword_lc = keyword.strip().lower() if keyword else ""
    for conv in convs:
        lines = _extract_visible_messages(conv)
        if keyword_lc and not _matches_keyword(lines, conv, keyword_lc):
            continue
        block = _format_one_block(conv, lines, omnipotent)
        if block:
            blocks.append(block)
    return blocks


def _extract_visible_messages(conv) -> list[str]:
    """Return the last _MAX_MESSAGES_PER_CONV visible messages as
    'Role: content' lines."""
    messages = getattr(conv, "value", None) or []
    visible = [
        m
        for m in messages
        if isinstance(m, dict)
        and m.get("role") in ("user", "assistant")
        and m.get("metadata_type") != "proactive_trigger"
    ]
    tail = visible[-_MAX_MESSAGES_PER_CONV:]
    result: list[str] = []
    for m in tail:
        role = "You" if m.get("role") == "assistant" else "User"
        content = str(m.get("content", ""))[:_MSG_CHAR_LIMIT].strip()
        if content:
            result.append(f"{role}: {content}")
    return result


def _matches_keyword(
    lines: list[str], conv, keyword_lc: str,
) -> bool:
    """Return True when the keyword appears in message lines or title."""
    for line in lines:
        if keyword_lc in line.lower():
            return True
    title = str(getattr(conv, "title", "") or "").lower()
    return keyword_lc in title


def _format_one_block(conv, lines: list[str], omnipotent: bool) -> str:
    """Format a single conversation as a labeled text block."""
    if not lines:
        return ""
    when = _resolve_block_when(conv)
    sid = getattr(conv, "session_id", "?")
    header = f"[{when} — session {sid}]"
    if omnipotent:
        chatbot_name = _resolve_chatbot_name(conv)
        if chatbot_name:
            header += f" ({chatbot_name})"
    return header + "\n" + "\n".join(lines)


def _resolve_block_when(conv) -> str:
    """Return a relative-time label for a conversation via its session."""
    try:
        from airunner_services.database.models.chat_session import (
            ChatSession,
        )

        sid = getattr(conv, "session_id", None)
        if sid is None:
            return "unknown"
        sess = ChatSession.objects.get(sid)
        if sess is None or not sess.last_message_at:
            return "unknown"
        return relative_time_ago(sess.last_message_at.isoformat())
    except Exception:
        return "unknown"


def _resolve_chatbot_name(conv) -> str:
    """Return the chatbot's name for a conversation, or '' on failure."""
    try:
        from airunner_services.database.models.chatbot import Chatbot

        cid = getattr(conv, "chatbot_id", None)
        if cid is None:
            return ""
        bot = Chatbot.objects.get(cid)
        if bot is None:
            return ""
        return str(getattr(bot, "name", "") or "")
    except Exception:
        return ""
