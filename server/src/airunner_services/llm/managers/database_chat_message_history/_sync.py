"""Event-recording helpers that stream conversation state to clients.

These module-level recorders were moved verbatim from the former
monolithic ``database_chat_message_history.py`` module.
"""

from typing import Any


def _record_message_append(
    conversation: Any,
    message_dict: dict,
    role: str,
) -> None:
    """Record a message_append event after a user or assistant message."""
    try:
        from airunner_services.events.recorder import record

        chatbot_id = getattr(conversation, "chatbot_id", None)
        conversation_id = getattr(conversation, "id", None)
        session_id = getattr(conversation, "session_id", None)
        if not chatbot_id:
            return
        record(
            "message_append",
            chatbot_id=chatbot_id,
            actor=role,
            payload={
                "role": role,
                "content": message_dict.get("content", ""),
                "thinking_content": message_dict.get("thinking_content"),
                "metadata_type": message_dict.get("metadata_type"),
                "tool_usage": message_dict.get("tool_usage"),
            },
            conversation_id=conversation_id,
            session_id=session_id,
            sequence_num=_visible_sequence(conversation),
        )
    except Exception:
        pass


def _record_tool_call(
    conversation: Any,
    tool_calls_dict: dict,
) -> None:
    """Record a tool_call event after an AIMessage tool_calls entry."""
    try:
        from airunner_services.events.recorder import record

        chatbot_id = getattr(conversation, "chatbot_id", None)
        conversation_id = getattr(conversation, "id", None)
        session_id = getattr(conversation, "session_id", None)
        if not chatbot_id:
            return
        tool_calls = tool_calls_dict.get("tool_calls", [])
        for tc in tool_calls:
            record(
                "tool_call",
                chatbot_id=chatbot_id,
                actor="assistant",
                payload={
                    "tool_name": tc.get("name", "unknown"),
                    "tool_id": tc.get("id", ""),
                    "query": str(tc.get("args", "")),
                    "details": None,
                },
                conversation_id=conversation_id,
                session_id=session_id,
            )
    except Exception:
        pass


def _record_tool_result(
    conversation: Any,
    tool_result_dict: dict,
) -> None:
    """Record a tool_result event after a ToolMessage is persisted."""
    try:
        from airunner_services.events.recorder import record

        chatbot_id = getattr(conversation, "chatbot_id", None)
        conversation_id = getattr(conversation, "id", None)
        session_id = getattr(conversation, "session_id", None)
        if not chatbot_id:
            return
        record(
            "tool_result",
            chatbot_id=chatbot_id,
            actor="system",
            payload={
                "tool_name": tool_result_dict.get("name", "unknown"),
                "tool_id": tool_result_dict.get("tool_call_id", ""),
                "result_len": len(str(tool_result_dict.get("content", ""))),
                "status": "success",
            },
            conversation_id=conversation_id,
            session_id=session_id,
        )
    except Exception:
        pass


def _visible_sequence(conversation: Any) -> int:
    """Return the count of visible (user/assistant) messages in value."""
    try:
        value = getattr(conversation, "value", None) or []
        count = 0
        for msg in value:
            if isinstance(msg, dict) and msg.get("role") in (
                "user",
                "assistant",
            ):
                count += 1
        return count
    except Exception:
        return 0
