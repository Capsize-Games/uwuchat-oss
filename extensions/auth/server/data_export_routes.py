"""GDPR / CCPA data export — self-service JSON portability.

Mounted at ``/api/v1/auth``.  Provides a single GET endpoint that
requires authentication and returns a downloadable JSON file containing
all data tied to the requesting account.

Rate-limited to 3 requests per day per account.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from airunner_services.data.tenant import (
    tenant_key_from_schema,
    tenant_scope,
)
from airunner_services.database.session import (
    public_session_scope,
    session_scope,
)
from extensions.auth.server.dependencies import require_auth
from extensions.auth.server.limiter import limiter
from extensions.auth.server.models import Account

router = APIRouter()

logger = logging.getLogger(__name__)


def _serialize_datetime(value: object) -> str | None:
    """Convert a datetime to ISO-8601 string, or return None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


@router.get(
    "/data-export",
    summary="Export all account data as a downloadable JSON file",
)
@limiter.limit("3/day")
async def data_export(
    request: Request,
    account_id: int = Depends(require_auth),
) -> Response:
    """Collect and return the requesting user's data as a JSON download.

    Includes account info, chatbots, conversation history (decrypted),
    and agent memory summaries (decrypted).
    """
    # -- Public schema: load the account record --------------------------
    with public_session_scope() as pub:
        account = (
            pub.query(Account)
            .filter(Account.id == account_id)
            .first()
        )
        if account is None:
            raise HTTPException(
                status_code=404, detail="Account not found"
            )

        tenant_schema = account.tenant_schema

    # -- Build account record (exclude password_hash) -------------------
    account_data = {
        "id": account.id,
        "email": account.email,
        "username": account.username,
        "auth_provider": account.auth_provider,
        "created_at": _serialize_datetime(account.created_at),
        "last_login": _serialize_datetime(account.last_login),
        "is_verified": account.is_verified,
    }

    # -- Tenant-scoped data ---------------------------------------------
    tenant_key = tenant_key_from_schema(str(tenant_schema))

    with tenant_scope(tenant_key):
        # Late imports so the ORM tables are resolved against the
        # correct tenant search_path (set by tenant_scope above).
        from airunner_services.database.models.agent_memory import (
            AgentMemory,
        )
        from airunner_services.database.models.chatbot import (
            Chatbot,
        )
        from airunner_services.database.models.conversation_turn import (
            ConversationTurn,
        )

        with session_scope() as sess:
            chatbots = sess.query(Chatbot).all()

            chatbot_data = []
            for cb in chatbots:
                chatbot_data.append({
                    "id": cb.id,
                    "name": cb.name,
                    "botname": cb.botname,
                    "bot_personality": cb.bot_personality,
                    "backstory": cb.backstory,
                    "gender": cb.gender,
                    "species": cb.species,
                    "created_at": _serialize_datetime(
                        getattr(cb, "created_at", None),
                    ),
                })

            # Read via ORM so EncryptedText decrypts transparently.
            turns = sess.query(ConversationTurn).all()
            conversation_data = []
            for turn in turns:
                conversation_data.append({
                    "id": turn.id,
                    "chatbot_id": turn.chatbot_id,
                    "conversation_id": turn.conversation_id,
                    "session_id": turn.session_id,
                    "role": turn.role,
                    "content": turn.content,
                    "turn_index": turn.turn_index,
                    "created_at": _serialize_datetime(turn.created_at),
                })

            # Read via ORM so EncryptedText decrypts transparently.
            memories = sess.query(AgentMemory).all()
            memory_data = []
            for mem in memories:
                memory_data.append({
                    "id": mem.id,
                    "chatbot_id": mem.chatbot_id,
                    "summary": mem.summary,
                    "updated_at": _serialize_datetime(mem.updated_at),
                })

    # -- Compose and return ---------------------------------------------
    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "account": account_data,
        "chatbots": chatbot_data,
        "conversation_turns": conversation_data,
        "agent_memories": memory_data,
    }

    body = json.dumps(payload, indent=2, ensure_ascii=False)

    return Response(
        content=body,
        media_type="application/json",
        headers={
            "Content-Disposition": (
                "attachment; filename=uwuchat-data-export.json"
            ),
        },
    )
