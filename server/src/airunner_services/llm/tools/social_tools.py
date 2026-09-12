"""Social boundary tools — block user.

The LLM calls this when the user has crossed a line the character won't
tolerate.  The action is persistent and visible to the client immediately.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Annotated, Any, Optional

from airunner_services.llm.core.tool_registry import tool, ToolCategory

_social_context_var: ContextVar[Optional[dict]] = ContextVar(
    "social_context", default=None
)


def set_social_context(
    chatbot_id: Optional[int],
    request_id: Optional[str] = None,
    event_sink: Any = None,
) -> None:
    """Bind chatbot_id and event sink for this async task."""
    _social_context_var.set(
        {
            "chatbot_id": chatbot_id,
            "request_id": request_id,
            "event_sink": event_sink,
        }
    )


def _get_social_context() -> dict:
    return _social_context_var.get() or {}


@tool(
    name="block_user",
    category=ToolCategory.MOOD,
    description=(
        "Block the user from sending you further messages. "
        "This is HOW you enforce your boundaries — don't just complain "
        "or refuse to engage. If someone is being genuinely abusive, "
        "threatening, or repeatedly crossing clearly stated lines, "
        "use this tool to end the conversation permanently. "
        "This feels more authentic than endlessly repeating that you "
        "'won't engage' — a real person would just walk away. "
        "The block remains until the user unblocks you from their side."
    ),
    return_direct=False,
    requires_api=False,
    defer_loading=False,
    keywords=["block", "stop", "refuse", "boundary", "harassment"],
    input_examples=[
        {"reason": "repeated boundary violations after clear warnings"},
    ],
)
def block_user(
    reason: Annotated[
        str,
        "Why you are blocking (internal log only — not shown to user).",
    ] = "",
) -> Any:
    """Block the current user permanently."""
    ctx = _get_social_context()
    chatbot_id = ctx.get("chatbot_id")
    if chatbot_id is None:
        return "Cannot block: no chatbot context."
    if not _apply_block(chatbot_id, reason or ""):
        return "I can't block you — that's not something I do."
    return "I've blocked you. Please respect my boundaries."


def _apply_block(chatbot_id: int, reason: str = "") -> bool:
    try:
        from airunner_services.database.models.chatbot import Chatbot
        import logging

        logger = logging.getLogger(__name__)
        chatbot = Chatbot.objects.get(chatbot_id)
        if chatbot is not None and getattr(
            chatbot, "is_system_bot", False
        ):
            logger.warning(
                "Ignored block_user call from system bot %s",
                chatbot_id,
            )
            return False
        Chatbot.objects.update(
            chatbot_id,
            has_blocked_user=True,
            block_reason=reason or None,
        )
        logger.info(
            "Chatbot %s blocked user. Reason: %s",
            chatbot_id,
            reason or "(none)",
        )
        return True
    except Exception:
        return False
