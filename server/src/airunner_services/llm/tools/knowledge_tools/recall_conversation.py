"""recall_conversation — search past conversation turns by semantic similarity.

NOT REGISTERED AS A CALLABLE TOOL — see knowledge_tools/__init__.py.
ConversationTurn (the table this searches) is only populated by a
session-close indexing job that has never fired successfully in this
codebase (0 rows, always), so this tool always returns "not found"
regardless of query correctness. Kept in place, unregistered, for when
that indexing gap is fixed — the search logic itself (date-range
filtering, pgvector similarity, keyword fallback) is correct.

Part of the UwU 'person search engine': lets the LLM proactively retrieve
what was said in earlier sessions.  Turns are indexed into ConversationTurn
at session-close.

Search strategy:
  1. If an embedding model is available via api, embed any unindexed turns
     lazily, then do pgvector cosine-distance search.
  2. Fall back to SQL ILIKE keyword search if no embedding model is present
     (e.g. during tests or when RAG is not loaded).

Date-anchored queries ("yesterday", "today", "last week", weekday names,
"N days ago") are parsed into a UTC date range and applied as a filter on
ConversationTurn.created_at in both search paths.
"""

from datetime import datetime, timedelta
from typing import Annotated, Any, Optional, Tuple

from airunner_services.llm.core.tool_registry import ToolCategory, tool
from airunner_services.llm.managers.prompt_builder.per_turn_temporal import (
    relative_time_ago,
)
from airunner_services.settings import AIRUNNER_LOG_LEVEL
from airunner_services.utils.application import get_logger

logger = get_logger(__name__, AIRUNNER_LOG_LEVEL)

_BATCH_EMBED_LIMIT = 200


@tool(
    name="recall_conversation",
    category=ToolCategory.RECALL,
    description=(
        "Search past conversations for something the user or you said in "
        "a previous session.  Use this when you want to remember a topic "
        "you discussed before, something the user told you, or how you "
        "responded to something earlier."
    ),
    return_direct=False,
    requires_api=False,
    defer_loading=False,
    keywords=[
        "remember",
        "last time",
        "we talked",
        "you told me",
        "earlier",
        "previous",
        "before",
        "we discussed",
        "yesterday",
        "today",
        "last week",
        "this morning",
    ],
    input_examples=[
        {"query": "what did we talk about last time"},
        {"query": "did the user mention their job"},
        {"query": "what happened at the pond"},
    ],
)
def recall_conversation(
    query: Annotated[str, "What to search for in past conversations"],
    max_results: Annotated[int, "Maximum turns to return"] = 6,
    api: Any = None,
) -> str:
    """Search past conversation turns for relevant context."""
    try:
        from airunner_services.database.models.conversation_turn import (
            ConversationTurn,
        )
        from airunner_services.knowledge_context import (
            get_knowledge_chatbot_id,
        )

        chatbot_id = get_knowledge_chatbot_id()
        if not chatbot_id:
            return "No chatbot context available."

        date_range = _resolve_date_range(query, chatbot_id)

        embedding_model = _resolve_embedding_model(api)
        if embedding_model is not None:
            _lazy_embed_turns(ConversationTurn, chatbot_id, embedding_model)
            results = _vector_search(
                ConversationTurn, chatbot_id, query,
                embedding_model, max_results, date_range,
            )
        else:
            results = _keyword_search(
                ConversationTurn, chatbot_id, query, max_results,
                date_range,
            )

        if not results:
            if date_range:
                label = _format_date_range_label(date_range, query)
                return f"No conversation found from {label}."
            return f"No past conversations found matching: '{query}'."

        lines: list[str] = []
        for turn in results:
            role = "You" if turn.role == "assistant" else "User"
            content = str(turn.content or "")[:250].strip()
            when = relative_time_ago(turn.created_at.isoformat())
            lines.append(f"- ({when}) {role}: {content}")
        return "\n".join(lines)
    except Exception as exc:
        logger.error("recall_conversation failed: %s", exc)
        return f"Error searching past conversations: {exc}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_date_range(
    query: str, chatbot_id: int,
) -> Optional[Tuple[datetime, datetime]]:
    """Parse a relative-date range from ``query`` using the chatbot's
    timezone, or return None if no date phrase is detected."""
    try:
        from airunner_services.database.models.chatbot import Chatbot
        from airunner_services.world.temporal_query import (
            parse_relative_date_range,
            resolve_reference_datetime,
        )

        chatbot = Chatbot.objects.get(chatbot_id)
        if chatbot is None:
            return None
        reference_dt = resolve_reference_datetime(chatbot)
        return parse_relative_date_range(query, reference_dt)
    except Exception:
        return None


def _format_date_range_label(
    date_range: Tuple[datetime, datetime], query: str,
) -> str:
    """Return a human-friendly label like 'yesterday (Mon Jul 6)'.

    Uses the start of the range and the query text to guess which
    relative label applies, then appends the actual date for clarity.
    """
    start = date_range[0]
    date_part = start.strftime("%a %b %-d")
    text = query.lower()
    if "yesterday" in text or "last night" in text:
        return f"yesterday ({date_part})"
    if "today" in text or "this morning" in text or (
        "earlier" in text and "today" in text
    ):
        return f"today ({date_part})"
    for name in (
        "monday", "tuesday", "wednesday", "thursday",
        "friday", "saturday", "sunday",
    ):
        if name in text:
            return f"{name} ({date_part})"
    if "this week" in text or "last week" in text:
        # date_range is half-open [start, end); the last included day
        # is end - 1 day.
        end = date_range[1] - timedelta(days=1)
        return f"{start:%b %d} to {end:%b %d}"
    import re
    if re.search(r"\d+\s+days?\s+ago", text):
        return f"{date_part}"
    return f"{start:%b %d} to {date_range[1]:%b %d}"


def _resolve_embedding_model(api: Any):
    """Return the embedding model from the api object, or None."""
    if api is None:
        return None
    return getattr(api, "embedding", None)


def _lazy_embed_turns(model, chatbot_id: int, embedding_model) -> None:
    """Compute and store encrypted embeddings for unindexed turns."""
    try:
        unindexed = (
            model.objects.query()
            .filter(
                model.chatbot_id == chatbot_id,
                model.embedding_enc.is_(None),
            )
            .limit(_BATCH_EMBED_LIMIT)
            .all()
        )
        if not unindexed:
            return

        from airunner_services.data.tenant import get_account_id
        from airunner_services.llm.managers.agent.pgvector_store import (
            embed_passages,
        )
        from airunner_services.utils.crypto.fhe_account_context import (
            get_or_create_public_context,
        )
        from airunner_services.utils.crypto.fhe_helpers import (
            encrypt_embedding,
            l2_normalize,
        )

        account_id = get_account_id()
        if account_id is None:
            return

        public_ctx = get_or_create_public_context(account_id)
        texts = [str(t.content or "") for t in unindexed]
        vectors = embed_passages(embedding_model, texts)

        with model.objects.transaction() as tx:
            for turn, vec in zip(unindexed, vectors):
                normalized = l2_normalize(vec)
                encrypted = encrypt_embedding(normalized, public_ctx)
                tx.query(model).filter(model.id == turn.id).update(
                    {"embedding_enc": encrypted},
                    synchronize_session=False,
                )
    except Exception as exc:
        from airunner_services.utils.network_retry import (
            is_transient_network_error,
            log_network_failure,
        )
        if is_transient_network_error(exc):
            log_network_failure(
                logger, "_lazy_embed_turns failed", exc
            )
        else:
            logger.error(
                "_lazy_embed_turns failed", exc_info=True
            )


def _vector_search(
    model, chatbot_id: int, query: str,
    embedding_model, limit: int,
    date_range: Optional[Tuple[datetime, datetime]] = None,
):
    """FHE-encrypted vector search over embedded turns."""
    from airunner_services.data.tenant import get_account_id
    from airunner_services.llm.managers.agent.pgvector_store import (
        embed_query,
    )
    from airunner_services.utils.crypto.fhe_helpers import (
        l2_normalize,
    )
    from airunner_services.utils.crypto.fhe_search import (
        FHE_CANDIDATE_CAP,
        fhe_similarity_rank,
    )

    account_id = get_account_id()
    if account_id is None:
        return []

    query_vector = embed_query(embedding_model, query)
    normalized_query = l2_normalize(query_vector)

    q = (
        model.objects.query()
        .filter(
            model.chatbot_id == chatbot_id,
            model.embedding_enc.isnot(None),
        )
    )
    if date_range is not None:
        q = q.filter(
            model.created_at >= date_range[0],
            model.created_at < date_range[1],
        )
    candidates = (
        q.order_by(model.created_at.desc())
        .limit(FHE_CANDIDATE_CAP)
        .all()
    )

    if not candidates:
        return []

    scored = fhe_similarity_rank(
        candidates,
        get_ciphertext=lambda t: t.embedding_enc,
        account_id=account_id,
        normalized_query=normalized_query.tolist(),
        top_k=limit,
    )
    return [turn for turn, _score in scored]


def _keyword_search(
    model, chatbot_id: int, query: str, limit: int,
    date_range: Optional[Tuple[datetime, datetime]] = None,
):
    """Return recent turns — content is encrypted, ILIKE cannot match.

    When ``date_range`` is provided, filters by ConversationTurn.created_at
    and returns the most recent matching turns (date-range filtering is a
    real, meaningful constraint, unlike keyword matching on encrypted
    content).  When ``date_range`` is None, falls back to returning the
    most recent turns unfiltered so the caller gets context even without
    embedding support — this is better than returning nothing, which would
    mislead the LLM into thinking there are no past conversations at all.
    """
    base = (
        model.objects.query()
        .filter(model.chatbot_id == chatbot_id)
    )
    if date_range is not None:
        base = base.filter(
            model.created_at >= date_range[0],
            model.created_at < date_range[1],
        )
    return base.order_by(model.id.desc()).limit(limit).all()
