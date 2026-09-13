"""Conversation Flow Inspector — REST API routes.

Endpoints:
- GET  /api/v1/conversation_inspector/conversations
- GET  /api/v1/conversation_inspector/flow/{conversation_id}
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from airunner_services.data.tenant import (
    reset_tenant_key,
    set_tenant_key,
    tenant_key_from_schema,
)
from airunner_services.database.models.conversation import Conversation
from airunner_services.database.session import (
    public_session_scope,
)
from airunner_services.settings import AIRUNNER_LOG_LEVEL
from airunner_services.utils.application.get_logger import get_logger

from extensions.conversation_inspector.server.dependencies import (
    require_superuser,
)
from extensions.conversation_inspector.server.flow_reconstructor import (
    reconstruct_flow,
)

router = APIRouter()
logger = get_logger(__name__, AIRUNNER_LOG_LEVEL)


# ── Response schemas ─────────────────────────────────────────────────


class ConversationSummary(BaseModel):
    id: int
    title: Optional[str]
    user_name: str
    chatbot_name: str
    message_count: int
    created_at: Optional[str]
    updated_at: Optional[str]


class ConversationListResponse(BaseModel):
    conversations: List[ConversationSummary]


class FlowStep(BaseModel):
    type: str
    label: str
    content: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class TurnData(BaseModel):
    turn_index: int
    user_message: Optional[Dict[str, Any]]
    system_prompt: Optional[Dict[str, Any]]
    rag_context: Optional[Dict[str, Any]]
    flow_steps: List[FlowStep]
    total_tokens: int = 0
    total_characters: int = 0
    conv_id: Optional[int] = None


class ConversationFlowResponse(BaseModel):
    conversation_id: int
    title: Optional[str]
    user_name: str
    chatbot: Optional[Dict[str, Any]]
    turns: List[TurnData]
    total_tokens: int = 0
    total_characters: int = 0


# ── Tenant helpers ────────────────────────────────────────────────────

# Synthetic account id used to inspect the pre-auth ``tenant_anonymous``
# schema. Conversations created before the multi-tenant WebSocket fix (or
# in any unauthenticated context) live there; real accounts always have a
# positive id, so 0 is a safe sentinel.
ANONYMOUS_ACCOUNT_ID = 0


def _resolve_tenant_schema_for_user(user_id: int) -> str | None:
    """Look up the tenant schema for one account by ID.

    Returns None if the account is not found.
    """
    from extensions.auth.server.models import Account

    with public_session_scope() as session:
        account = (
            session.query(Account).filter(Account.id == user_id).first()
        )
        if account is None:
            return None
        return account.tenant_schema


@contextmanager
def _tenant_context(user_id: int):
    """Switch to the schema for one account (or the anonymous bucket).

    Yields ``True`` when a schema was activated, ``False`` when the
    account id does not resolve to a known account. Restores the previous
    tenant context on exit in all cases.

    Note: this intentionally activates **exactly one** schema. The earlier
    implementation also merged ``tenant_anonymous`` into every account's
    result set, which mis-attributed unrelated pre-auth conversations to
    whichever account was selected. Anonymous conversations are now only
    visible via the explicit ``ANONYMOUS_ACCOUNT_ID`` bucket.
    """
    if user_id == ANONYMOUS_ACCOUNT_ID:
        token = set_tenant_key(None)  # → tenant_anonymous
        try:
            yield True
        finally:
            reset_tenant_key(token)
        return

    schema = _resolve_tenant_schema_for_user(user_id)
    if schema is None:
        yield False
        return

    token = set_tenant_key(tenant_key_from_schema(schema))
    try:
        yield True
    finally:
        reset_tenant_key(token)


# ── Routes ───────────────────────────────────────────────────────────


@router.get(
    "/conversations",
    response_model=ConversationListResponse,
    summary="List conversations for a user",
)
async def list_conversations(
    account_id: int = Depends(require_superuser),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    q: str = Query("", description="Search by title or user name"),
    user_id: Optional[int] = Query(
        None, description="Filter by user/account ID"
    ),
):
    """Return conversations for a specific user (superuser only).

    When user_id is provided, the request switches to that user's tenant
    schema so their conversations are queried in the correct namespace.
    """
    del account_id  # unused — presence enforces auth

    if user_id is None:
        return ConversationListResponse(conversations=[])

    with _tenant_context(user_id) as resolved:
        if not resolved:
            raise HTTPException(
                status_code=404,
                detail=f"Account {user_id} not found",
            )
        results = _list_conversation_summaries(q, offset, limit)

    return ConversationListResponse(conversations=results)


@router.get(
    "/flow/{conversation_id}",
    response_model=ConversationFlowResponse,
    summary="Get flow for one conversation",
)
async def get_conversation_flow(
    conversation_id: int,
    account_id: int = Depends(require_superuser),
    user_id: Optional[int] = Query(
        None, description="User/account ID that owns the conversation"
    ),
):
    """Return the complete reconstructed flow for one conversation."""
    target_user = user_id if user_id is not None else account_id

    with _tenant_context(target_user) as resolved:
        if not resolved:
            raise HTTPException(
                status_code=404,
                detail=f"Account {user_id} not found",
            )

        conv = Conversation.objects.query().filter(
            Conversation.id == conversation_id,
        ).first()
        if conv is None:
            raise HTTPException(
                status_code=404,
                detail=f"Conversation {conversation_id} not found",
            )

        flow_data = reconstruct_flow(conv)
        return ConversationFlowResponse(**flow_data)


@router.get(
    "/flow/chatbot/{chatbot_id}",
    response_model=ConversationFlowResponse,
    summary="Get full thread flow for a chatbot (all session conversations)",
)
async def get_chatbot_thread_flow(
    chatbot_id: int,
    account_id: int = Depends(require_superuser),
    user_id: Optional[int] = Query(
        None, description="User/account ID that owns the conversations"
    ),
):
    """Return the full thread flow spanning all conversations for a chatbot."""
    target_user = user_id if user_id is not None else account_id

    with _tenant_context(target_user) as resolved:
        if not resolved:
            raise HTTPException(
                status_code=404,
                detail=f"Account {user_id} not found",
            )

        conversations = (
            Conversation.objects.query()
            .filter(Conversation.chatbot_id == chatbot_id)
            .order_by(Conversation.id.asc())
            .all()
        )

        if not conversations:
            raise HTTPException(
                status_code=404,
                detail=f"No conversations found for chatbot {chatbot_id}",
            )

        all_turns: List[dict] = []
        total_tokens = 0
        total_chars = 0
        chatbot_info = None
        user_name = ""

        for conv in conversations:
            flow_data = reconstruct_flow(conv)
            if chatbot_info is None and flow_data.get("chatbot"):
                chatbot_info = flow_data["chatbot"]
            user_name = flow_data.get("user_name", user_name)
            turns = flow_data.get("turns", [])
            for turn in turns:
                turn["conv_id"] = conv.id
            all_turns.extend(turns)
            total_tokens += flow_data.get("total_tokens", 0)
            total_chars += flow_data.get("total_characters", 0)

        # Re-index turns
        for i, turn in enumerate(all_turns):
            turn["turn_index"] = i

        return ConversationFlowResponse(
            conversation_id=0,  # multi-conversation: use 0
            title=f"Thread for chatbot {chatbot_id} ({len(conversations)} sessions)",
            user_name=user_name,
            chatbot=chatbot_info,
            turns=all_turns,
            total_tokens=total_tokens,
            total_characters=total_chars,
        )


# ── Helpers ───────────────────────────────────────────────────────────


def _list_conversation_summaries(
    q: str,
    offset: int,
    limit: int,
) -> List[ConversationSummary]:
    """Query and build ConversationSummary models via the query builder."""
    builder = Conversation.objects.query().order_by(
        Conversation.created_at.desc(),
    )
    if q:
        search = f"%{q}%"
        builder = builder.filter(
            (Conversation.title.ilike(search))
            | (Conversation.user_name.ilike(search)),
        )
    rows = builder.offset(offset).limit(limit).all()
    results: List[ConversationSummary] = []
    for conv in rows:
        msg_count = (
            len(conv.value) if isinstance(conv.value, list) else 0
        )
        results.append(
            ConversationSummary(
                id=conv.id,
                title=conv.title,
                user_name=conv.user_name or "Unknown",
                chatbot_name=conv.chatbot_name or "Unknown",
                message_count=msg_count,
                created_at=(
                    conv.created_at.isoformat()
                    if conv.created_at else None
                ),
                updated_at=(
                    conv.updated_at.isoformat()
                    if conv.updated_at else None
                ),
            )
        )
    return results
