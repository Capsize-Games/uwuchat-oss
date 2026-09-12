"""Random-chatbot creation Celery task (durable, resumable).

``generate_random_chatbot_task`` is enqueued by the
``POST /api/v1/llm/create-random-chatbot`` RPC handler right after it
creates the placeholder ``Chatbot`` row with
``creation_status="generating"``.  The task runs the existing server-side
character logic — ``randomize_character()`` → LLM identity generation
(the slow call) → row field update + greeting persistence — entirely in
the Celery worker, so it completes even if the browser that kicked it
off goes away mid-request.

Terminal states are persisted on the row (``ready`` / ``failed``) and
broadcast to the owning account via the ``uwu_creation`` WebSocket
event (Redis outbox → ``uwu_creation_ws_forwarder``).
"""

from __future__ import annotations

from airunner_services.data.tenant import tenant_scope
from airunner_services.tasks.celery_app import app
from celery.exceptions import MaxRetriesExceededError
from celery.utils.log import get_task_logger

from projects.uwuchat.server.tasks.random_chatbot_identity import (
    IdentityGenerationRejected,
    identity_fields,
    invoke_identity_llm,
)

logger = get_task_logger(__name__)


@app.task(
    bind=True,
    name=(
        "projects.uwuchat.server.tasks.random_chatbot_tasks."
        "generate_random_chatbot_task"
    ),
    max_retries=2,
    default_retry_delay=30,
)
def generate_random_chatbot_task(
    self, chatbot_id: int, tenant_key: str, account_id: int,
) -> dict:
    """Generate one random chatbot's identity, durably and resumably."""
    try:
        try:
            with tenant_scope(tenant_key):
                _run_generation(chatbot_id, account_id)
        except IdentityGenerationRejected:
            logger.warning(
                "Random chatbot identity rejected (chatbot=%d)", chatbot_id,
            )
            raise
        except Exception:
            logger.exception(
                "Random chatbot generation failed "
                "(chatbot=%d account=%d)", chatbot_id, account_id,
            )
            raise self.retry(countdown=30, max_retries=2)
    except (MaxRetriesExceededError, IdentityGenerationRejected):
        _mark_failed(chatbot_id, tenant_key, account_id)
        return {"status": "failed", "chatbot_id": chatbot_id}
    return {"status": "ready", "chatbot_id": chatbot_id}


def _run_generation(chatbot_id: int, account_id: int) -> None:
    """Run the full generation sequence for one chatbot row."""
    from airunner_services.api.routes.character_randomizer import (
        randomize_character,
    )
    from airunner_services.database.models.chatbot import (
        Chatbot,
        ChatbotCreationStatus,
    )
    from airunner_services.database.session import session_scope

    profile = randomize_character(allowed_species=None)
    identity = invoke_identity_llm(profile)
    fields, greeting = identity_fields(profile, identity)

    with session_scope() as session:
        row = session.query(Chatbot).get(chatbot_id)
        if row is None or getattr(row, "deleted", False):
            logger.warning("Random chatbot row %d missing", chatbot_id)
            return
        name = _unique_name(session, fields["name"])
        fields["name"] = name
        fields["botname"] = name
        for key, val in fields.items():
            setattr(row, key, val)
        row.creation_status = ChatbotCreationStatus.READY.value
        session.commit()

    if greeting:
        _persist_greeting(chatbot_id, greeting)
    _append_terminal_event(
        account_id, chatbot_id, "ready", name, greeting,
    )


def _persist_greeting(chatbot_id: int, greeting: str) -> None:
    """Persist the opening greeting; best-effort, never fatal."""
    from airunner_services.llm.session_manager import SessionManager

    try:
        SessionManager().persist_greeting(chatbot_id, greeting)
    except Exception:
        logger.exception(
            "Failed to persist greeting for chatbot %d", chatbot_id,
        )


def _unique_name(session, name: str) -> str:
    """Return *name*, suffixed until unique within this tenant.

    ``Chatbot.name`` is a unique column; two LLM calls can return the
    same name, so the task must not collide on the final write.
    """
    from airunner_services.database.models.chatbot import Chatbot

    candidate = name
    suffix = 2
    while True:
        clash = (
            session.query(Chatbot.id)
            .filter(
                Chatbot.name == candidate,
                Chatbot.deleted == False,
            )
            .first()
        )
        if clash is None:
            return candidate
        candidate = f"{name} ({suffix})"
        suffix += 1


def _mark_failed(chatbot_id: int, tenant_key: str, account_id: int) -> None:
    """Soft-delete the placeholder row and broadcast the failure.

    Also flips ``deleted=True`` (the same flag
    ``queryResources("Chatbot", {deleted: false})`` already filters
    on) — otherwise a failed generation leaves a permanent, unnamed
    "New Friend xxxxxxxx" ghost bot sitting in the contact list.
    """
    from airunner_services.database.models.chatbot import (
        Chatbot,
        ChatbotCreationStatus,
    )
    from airunner_services.database.session import session_scope

    with tenant_scope(tenant_key), session_scope() as session:
        row = session.query(Chatbot).get(chatbot_id)
        if row is not None:
            row.creation_status = ChatbotCreationStatus.FAILED.value
            row.deleted = True
            session.commit()
    _append_terminal_event(account_id, chatbot_id, "failed", "")


def _append_terminal_event(
    account_id: int,
    chatbot_id: int,
    status: str,
    name: str,
    greeting: str = "",
) -> None:
    """Append one terminal-status payload to the WS outbox.

    ``greeting`` rides along on the ``ready`` push so the client can
    populate ``greetingStore`` and replay the same synchronous
    greeting-animation path ``useConnectRandom`` used before this
    became an async job — see ``greetingStore.ts`` for why that
    fast-path exists (a render-ordering race window events can't
    reliably solve on their own).
    """
    from projects.uwuchat.server.uwu_creation_event_store import (
        uwu_creation_events_append,
    )

    uwu_creation_events_append({
        "account_id": account_id,
        "chatbot_id": chatbot_id,
        "status": status,
        "name": name,
        "greeting": greeting,
    })
