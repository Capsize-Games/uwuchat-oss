"""WebSocket RPC handler for durable random-chatbot creation.

The client's ``request()`` helper sends RPC messages over the unified
``/api/v1/events`` WebSocket, which the server dispatches via
``@_rpc_register`` — not the HTTP router.  See ``headlesscode_rpc.py``
for the same pattern.

``POST /api/v1/llm/create-random-chatbot`` creates the placeholder
``Chatbot`` row (``creation_status="generating"``) immediately and
enqueues :func:`generate_random_chatbot_task` before returning.  The
slow LLM identity generation runs entirely in the Celery worker, so it
survives the browser reloading or closing the tab mid-request.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from airunner_services.api.routes.events import (
    _rpc_error_response,
    _rpc_register,
)
from airunner_services.api.ws_tenant import resolve_ws_tenant

logger = logging.getLogger(__name__)

# Celery task that owns the slow LLM identity generation.  Referenced
# by name (not import) so this route module never hard-depends on the
# task module at import time — the worker imports it via the Celery
# ``include`` list in ``airunner_services.tasks.celery_app``.
_RANDOM_CHATBOT_TASK = (
    "projects.uwuchat.server.tasks.random_chatbot_tasks."
    "generate_random_chatbot_task"
)


def _account_id(ws: Any) -> int | None:
    """Return the socket's account id, or None when unauthenticated."""
    _tenant, account_id = resolve_ws_tenant(ws)
    return account_id


def _create_placeholder_row() -> int:
    """Insert the ``generating`` placeholder row, return its id.

    Unique placeholder name — ``Chatbot.name`` is a unique column, and
    two concurrent creations must not collide on the default.
    """
    from airunner_services.database.models.chatbot import (
        Chatbot,
        ChatbotCreationStatus,
    )
    from airunner_services.database.session import session_scope

    placeholder = f"New Friend {uuid.uuid4().hex[:8]}"
    with session_scope() as session:
        row = Chatbot(
            botname=placeholder,
            name=placeholder,
            creation_status=ChatbotCreationStatus.GENERATING.value,
        )
        session.add(row)
        session.commit()
        return row.id


def _enqueue_generation(ws: Any, account_id: int) -> dict[str, Any]:
    """Rate-limit, create the placeholder row, and queue the task."""
    from airunner_services.api.routes.rpc_settings._helpers import (
        _chatbot_rate_limit_error,
    )
    from airunner_services.data.tenant import get_tenant_key
    from airunner_services.database.models.chatbot import (
        ChatbotCreationStatus,
    )
    from airunner_services.tasks.celery_app import app

    err = _chatbot_rate_limit_error(ws)
    if err:
        return err

    tenant_key = get_tenant_key()
    if not tenant_key:
        return {
            "status": 500,
            "body": {"error": "Tenant context unavailable"},
        }

    chatbot_id = _create_placeholder_row()
    app.send_task(
        _RANDOM_CHATBOT_TASK, args=[chatbot_id, tenant_key, account_id],
    )
    return {
        "status": 200,
        "body": {
            "chatbot_id": chatbot_id,
            "creation_status": ChatbotCreationStatus.GENERATING.value,
        },
    }


@_rpc_register("POST", "/api/v1/llm/create-random-chatbot")
async def _rpc_create_random_chatbot(
    body: dict, ws: Any, **kw: Any,
) -> dict[str, Any]:
    """Create a Chatbot row and enqueue background character generation.

    Returns fast: the ``Chatbot`` row (``creation_status="generating"``)
    plus the queued Celery task are the durable record of the creation.
    The slow LLM identity call runs in the worker process, so it
    survives the browser reloading or closing the tab mid-generation.
    """
    del body
    account_id = _account_id(ws)
    if account_id is None:
        return {"status": 401, "body": {"error": "Authentication required"}}
    try:
        return _enqueue_generation(ws, account_id)
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="create-random-chatbot error",
        )
