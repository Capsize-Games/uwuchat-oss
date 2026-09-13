"""Code-mode toggle: per-conversation switch into coding-agent behavior.

Stored in ``conversation.user_data["code_mode"]`` — no migration,
mirroring the mood-persistence pattern in ``llm/mood/persistence.py``.
When on, the system-bot prompt swaps to ``code_mode_prompt.py`` (see
``prompt_builder/parts.py``'s ``_code_mode_active`` hook) instead of
the normal UwU persona.

``conversation.user_data["code_mode_slug"]`` (same JSON blob, separate
key) selects WHICH headlesscode mode a launched session runs in —
mirrors Zoo Code's mode picker. Read by ``launch_headlesscode_session``
(``tools/code_tools/launch_session.py``) as the effective ``mode``
argument. See ``CODE_MODE_SLUGS`` for the allowed values.
"""

from __future__ import annotations

import logging

from airunner_services.database.models.conversation import Conversation

logger = logging.getLogger(__name__)

DEFAULT_CODE_MODE_SLUG = "code"

# Every headlesscode mode UwUChat's admin harness can launch a session
# in — Zoo Code's built-ins ("code", "architect", "ask", "debug",
# "orchestrator") plus this repo's own custom modes from .roomodes
# ("planning", "zoo-audit", "script-agent", "qa-agent",
# "deepseek-reviewer", "multi-agent-orchestrator-headless"). Slugs here
# are passed straight through as headlesscode's `--mode` argument (see
# launch_session.py's `_resolve_effective_mode`) — extend here (and in
# CodeModePicker.tsx's MODE_META) if a new headlesscode mode gets a
# real use case.
CODE_MODE_SLUGS: tuple[str, ...] = (
    "code",
    "architect",
    "ask",
    "debug",
    "orchestrator",
    "planning",
    "zoo-audit",
    "script-agent",
    "qa-agent",
    "deepseek-reviewer",
    "multi-agent-orchestrator-headless",
)


def is_code_mode_enabled(conversation: Conversation) -> bool:
    """Return whether *conversation* has code mode turned on."""
    return bool((conversation.user_data or {}).get("code_mode", False))


def get_code_mode(conversation_id: int) -> bool:
    """Return code mode for a conversation id, False if not found."""
    conv = Conversation.objects.get(conversation_id)
    if conv is None:
        return False
    return is_code_mode_enabled(conv)


def get_code_mode_slug(conversation: Conversation) -> str:
    """Return *conversation*'s selected headlesscode mode slug."""
    slug = (conversation.user_data or {}).get("code_mode_slug")
    return slug if slug in CODE_MODE_SLUGS else DEFAULT_CODE_MODE_SLUG


def set_code_mode(
    conversation_id: int, enabled: bool, slug: str | None = None,
) -> tuple[bool, str]:
    """Persist code mode (+ optional slug) for a conversation id.

    Returns ``(enabled, slug)``. Raises ValueError if the conversation
    doesn't exist, or if *slug* is given and not one of
    ``CODE_MODE_SLUGS``.

    Side effect: enqueues the GPU inference-mode switch (fire-and-forget
    Celery task — see ``tasks/gpu_inference_tasks.py`` and
    plans/uwuchat-code-mode-gpu-model-switching.md Decision C). The RPC
    caller is waiting on this response, so the multi-second daemon
    stop/start runs asynchronously; the toggle returns immediately. The
    DIALOGUE routing check reads the persisted ``user_data["code_mode"]``
    (Decision B), so it converges to the correct model once the switch
    finishes.
    """
    if slug is not None and slug not in CODE_MODE_SLUGS:
        raise ValueError(f"Unknown code-mode slug: {slug!r}")
    conv = Conversation.objects.get(conversation_id)
    if conv is None:
        raise ValueError(f"Conversation {conversation_id} not found")
    ud = conv.user_data or {}
    ud["code_mode"] = bool(enabled)
    if slug is not None:
        ud["code_mode_slug"] = slug
    Conversation.objects.update(conversation_id, user_data=ud)
    _enqueue_gpu_switch(bool(enabled))
    return bool(enabled), ud.get("code_mode_slug", DEFAULT_CODE_MODE_SLUG)


def _enqueue_gpu_switch(enabled: bool) -> None:
    """Fire-and-forget enqueue of the GPU daemon switch.

    Never raises: a failure to enqueue is logged and swallowed so a
    broker hiccup cannot break the code-mode toggle itself (the
    persisted state is already correct; the GPU just won't converge
    until the next toggle).
    """
    try:
        from projects.uwuchat.server.tasks.gpu_inference_tasks import (
            apply_code_mode_gpu_switch,
        )

        apply_code_mode_gpu_switch.apply_async(args=[enabled])
        logger.info("Enqueued GPU switch: code_mode=%s", enabled)
    except Exception:
        logger.exception("Failed to enqueue GPU switch: code_mode=%s", enabled)


def code_mode_active_for_owner(owner) -> bool:
    """Return whether *owner*'s current conversation has code mode on.

    *owner* is the LLM manager building the prompt. The conversation id
    is set on the workflow manager (``WorkflowManager.set_conversation_id``)
    — the manager's own ``_conversation_id`` is never assigned — so fall
    back to ``owner._workflow_manager._conversation_id`` the same way
    ``prompt_builder/per_turn_bridge_retrieval.py`` does. Called from the
    framework prompt-builder and tool-selection layer, which do not know
    about code mode itself — see ``prompt_builder/parts.py``'s
    ``_code_mode_active``.
    """
    conv_id = getattr(owner, "_conversation_id", None)
    if not conv_id:
        wm = getattr(owner, "_workflow_manager", None)
        conv_id = getattr(wm, "_conversation_id", None) if wm else None
    if not conv_id:
        return False
    conv = Conversation.objects.get(conv_id)
    if conv is None:
        return False
    return is_code_mode_enabled(conv)
