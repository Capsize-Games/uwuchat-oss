"""LLM tool: launch_headlesscode_session — async headlesscode launch.

The tool function itself is a fast synchronous call: it validates the
named project is registered, checks code credits, and enqueues a
Celery task.  The actual headlesscode session lifecycle runs entirely
inside ``headlesscode_tasks.launch_headlesscode_session_task`` — never
blocking the agent loop here.

The task receives the current conversation id plus the project name so
it can (a) persist the ``headlesscode_sessions`` row with its
``conversation_id`` and (b) append a ``headlesscode_session`` card
entry to the conversation (Phase 5 — the client renders that entry as
a live session card).
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from airunner_services.data.tenant import get_account_id, get_tenant_key
from airunner_services.llm.core.tool_registry import ToolCategory, tool

from projects.uwuchat.server.code_credits_service import has_credits
from projects.uwuchat.server.models.headlesscode_project import (
    HeadlesscodeProject,
)
from projects.uwuchat.server.tools.code_tools.launch_confirmation import (
    consume_pending_confirmation,
    launch_idempotency_key,
    mark_pending_confirmation,
)

logger = logging.getLogger(__name__)

_NO_CREDITS_MESSAGE = (
    "I can't start a headlesscode session — there are no code "
    "credits left on the account. An admin needs to top them up."
)

# Headlesscode's local-backend env contract (mirrors src/cli.ts):
# the session runs on a local Ollama daemon (Qwen 3.5 9B — no cloud
# cost) when HEADLESSCODE_CODE_MODE_BACKEND=ollama AND the session's
# mode is in HEADLESSCODE_LOCAL_BACKEND_MODES (default "code").
_LOCAL_BACKEND_ENV = "HEADLESSCODE_CODE_MODE_BACKEND"
_LOCAL_BACKEND_MODES_ENV = "HEADLESSCODE_LOCAL_BACKEND_MODES"
_DEFAULT_LOCAL_BACKEND_MODES = "code"


def _uses_local_backend(mode: str | None) -> bool:
    """Return True when a session in *mode* runs on the local backend.

    Mirrors headlesscode's own decision (src/cli.ts): the local
    Ollama backend is active only when
    ``HEADLESSCODE_CODE_MODE_BACKEND=ollama`` and the mode is in the
    local-backend allow-list (``HEADLESSCODE_LOCAL_BACKEND_MODES``,
    default ``"code"``).  Local sessions have no dollar cost, so the
    credits gate must not apply to them.
    """
    import os

    if os.getenv(_LOCAL_BACKEND_ENV, "").strip().lower() != "ollama":
        return False
    modes_env = os.getenv(_LOCAL_BACKEND_MODES_ENV, "")
    modes = {
        m.strip() for m in modes_env.split(",")
    } if modes_env.strip() else {
        m.strip() for m in _DEFAULT_LOCAL_BACKEND_MODES.split(",")
    }
    return (mode or "code").strip() in modes


def _registered_project(project_name: str, user_id: int):
    """Return the user's registered project by name, or None."""
    projects = HeadlesscodeProject.objects.filter_by(
        user_id=user_id, name=project_name.strip(),
    )
    return projects[0] if projects else None


def _unregistered_message(project_name: str, user_id: int) -> str:
    """Build a helpful error listing the user's registered projects."""
    projects = HeadlesscodeProject.objects.filter_by(user_id=user_id)
    names = ", ".join(p.name for p in projects) or "none yet"
    return (
        f"'{project_name}' isn't a registered project. Registered "
        f"projects: {names}. The user can add one in settings."
    )


def _resolve_agent_context(agent: Any):
    """Return (user_id, chatbot_id) from the injected agent, or None."""
    user = getattr(agent, "user", None) if agent else None
    chatbot = getattr(agent, "chatbot", None) if agent else None
    user_id = getattr(user, "id", None) if user else None
    chatbot_id = getattr(chatbot, "id", None) if chatbot else None
    if not user_id or not chatbot_id:
        return None
    return user_id, chatbot_id


def _check_confirmation(
    idem_key: str, confirmed: bool, project_name: str, local: bool,
) -> str | None:
    """Enforce the real confirmation gate; return an error/ask string.

    Returns None when the caller should proceed with the launch.  For
    local-backend sessions (*local* True) the ask text does not mention
    prepaid credits — local sessions run on the user's own model and
    cost nothing.
    """
    if not confirmed:
        mark_pending_confirmation(idem_key)
        if local:
            return (
                "CONFIRM_REQUIRED: starting a headlesscode session on "
                f"'{project_name}' runs locally on the user's model "
                "for several minutes. Ask the user to confirm, then "
                "call launch_headlesscode_session again with "
                "confirmed=true."
            )
        return (
            "CONFIRM_REQUIRED: starting a headlesscode session on "
            f"'{project_name}' spends prepaid code credits and runs "
            "for several minutes. Ask the user to confirm, then call "
            "launch_headlesscode_session again with confirmed=true."
        )
    if not consume_pending_confirmation(idem_key):
        return (
            "I can't start that session yet — I need to ask the user "
            "to confirm first. Call launch_headlesscode_session again "
            "with confirmed=false to ask them."
        )
    return None


def _resolve_conversation_id(chatbot_id: int) -> int | None:
    """Return the chatbot's current conversation id, or None.

    Resolved the same way ``DatabaseChatMessageHistory`` finds its
    conversation (``current=True``), scoped to this chatbot so a
    launch from a non-current chatbot can't stamp the wrong thread.
    """
    try:
        from airunner_services.database.models.conversation import (
            Conversation,
        )

        conv = (
            Conversation.objects.query()
            .filter(
                Conversation.chatbot_id == chatbot_id,
                Conversation.current.is_(True),
            )
            .order_by(Conversation.id.desc())
            .first()
        )
        if conv is not None:
            return getattr(conv, "id", None)
    except Exception:
        logger.debug(
            "Headlesscode launch: could not resolve conversation id",
            exc_info=True,
        )
    return None


def _resolve_effective_mode(
    conversation_id: int | None, tool_mode: str | None,
) -> str:
    """Return the headlesscode mode to launch with.

    The conversation's mode-picker selection (``code_mode_service``'s
    ``code_mode_slug`` — set via the bottom-left mode picker in the
    UI, mirroring Zoo Code) is authoritative when a conversation is
    resolved. *tool_mode* (the model's own ``mode`` argument) is only
    a fallback for the rare case where no conversation is resolved
    yet; the model is told not to guess a mode in the system prompt.
    """
    if conversation_id is not None:
        from airunner_services.database.models.conversation import (
            Conversation,
        )

        from projects.uwuchat.server.code_mode_service import (
            get_code_mode_slug,
        )

        conv = Conversation.objects.get(conversation_id)
        if conv is not None:
            return get_code_mode_slug(conv)
    return tool_mode or "code"


def _enqueue_launch(
    project_id: int,
    chatbot_id: int,
    project_name: str,
    task: str,
    mode: str | None,
    account_id: int,
    idem_key: str,
    conversation_id: int | None,
) -> str:
    """Enqueue the headlesscode launch task and return a confirmation."""
    from projects.uwuchat.server.tasks.headlesscode_tasks import (
        launch_headlesscode_session_task,
    )

    launch_headlesscode_session_task.apply_async(
        args=[
            project_id, chatbot_id, task, mode,
            get_tenant_key(), account_id, idem_key,
            conversation_id, project_name,
        ],
    )
    return (
        f"Started a headlesscode session on '{project_name}' for: "
        f"{task[:80]}. Let the user know it's running."
    )


@tool(
    name="launch_headlesscode_session",
    category=ToolCategory.CODE,
    description=(
        "Start a headless coding-agent session against a project the "
        "user has already registered. Call this when the user asks to "
        "start/launch/run a coding session, an agent task, or "
        "automated dev work on a registered project. Requires one "
        "explicit user confirmation before launching: call with "
        "confirmed=false first, ask the user to confirm, then call "
        "again with confirmed=true only after they agree. Local-backend "
        "sessions run on the user's own model at no cost; cloud "
        "sessions spend prepaid code credits."
    ),
    return_direct=False,
    requires_agent=True,
    defer_loading=True,
    keywords=[
        "headlesscode", "coding agent", "code session", "agent session",
        "launch session", "start working on", "automated dev work",
    ],
    input_examples=[
        {
            "project_name": "acme-web",
            "task": "Fix the login bug in the auth module",
        },
    ],
)
def launch_headlesscode_session(
    project_name: Annotated[
        str,
        "Exact name of the registered project to work on, from the "
        "user's project registry.",
    ],
    task: Annotated[
        str,
        "Short description of the coding work the agent should do.",
    ],
    mode: Annotated[
        str | None,
        "Do not set this — the user's mode-picker selection for this "
        "conversation (code/architect) is used automatically. Only a "
        "fallback for the rare case where no conversation is resolved.",
    ] = None,
    confirmed: Annotated[
        bool,
        "False on first call. Set to true ONLY after the user "
        "explicitly confirmed they want to launch the session.",
    ] = False,
    agent: Any = None,
) -> str:
    """Validate the project, gate on credits/confirmation, enqueue."""
    context = _resolve_agent_context(agent)
    if context is None:
        return (
            "I couldn't start that session — something's off with my "
            "session context. Can we try again?"
        )
    user_id, chatbot_id = context

    project = _registered_project(project_name, user_id)
    if project is None:
        return _unregistered_message(project_name, user_id)

    if not task.strip():
        return (
            "I can't start a session without knowing what to work on. "
            "Ask the user what task they want done."
        )

    conversation_id = _resolve_conversation_id(chatbot_id)
    effective_mode = _resolve_effective_mode(conversation_id, mode)
    local = _uses_local_backend(effective_mode)

    # Local-backend sessions (Qwen 3.5 9B on the user's own daemon) have
    # no dollar cost — skip the account/credits gate entirely.  Only
    # cloud sessions need a credit check.
    if not local:
        account_id = get_account_id()
        if not account_id:
            return (
                "I couldn't start that session — I can't verify your "
                "code credits right now. Try again in a moment."
            )
        if not has_credits(account_id):
            return _NO_CREDITS_MESSAGE
    else:
        account_id = 0

    idem_key = launch_idempotency_key(chatbot_id, project.id, task)
    confirm_result = _check_confirmation(
        idem_key, confirmed, project_name, local,
    )
    if confirm_result is not None:
        return confirm_result

    # A chat-triggered launch is always a single bounded task, not a
    # multi-repo orchestration run — the dashboard's own default
    # ("multi-agent-orchestrator-headless", session-launch.ts) is for
    # the standalone CLI dashboard's own use case. Defaulting to "code"
    # here also matters for the local backend specifically: cli.ts's
    # HEADLESSCODE_CODE_MODE_BACKEND override only applies when
    # mode == "code", so leaving mode unset would silently run this
    # session on OpenRouter regardless of that env var.
    return _enqueue_launch(
        project.id, chatbot_id, project_name, task.strip(), effective_mode,
        account_id, idem_key, conversation_id,
    )
