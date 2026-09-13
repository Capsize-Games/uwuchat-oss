"""Minimal forced-response utilities retained for agentic-loop fallback.

The bulk of the old force_response_node logic has been removed because
the agentic loop lets the model see tool results inline and decide
itself what to do next.  Only the in-character response path and a
few static message utilities are kept.
"""

from __future__ import annotations

from typing import Any, Dict, List

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

_IN_CHARACTER_FALLBACK = (
    "I'm sorry, but I wasn't able to process that properly. "
    "Could you try asking again?"
)


class NodeForcedResponseHelper:
    """Handle legacy forced-response dispatch (kept for compatibility)."""

    def __init__(self, owner: Any) -> None:
        """Store the owning workflow manager."""
        self._owner = owner

    # ------------------------------------------------------------------
    # The only retained logic: in-character response for final fallback
    # ------------------------------------------------------------------

    def force_response_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Generate one forced final response (no-op in agentic loop).

        The agentic loop now routes model→tools→model internally.
        This node is kept as a safety net but is not wired into the
        default graph.  If called, it delegates to the agentic guard.
        """
        user_question = self.get_user_question(state["messages"])
        prompt = self._build_clean_history(
            state["messages"], user_question
        )
        generation_kwargs = state.get("generation_kwargs", {})
        try:
            response = self._owner._stream_model_response(
                prompt, generation_kwargs
            )
            if response is not None:
                return {
                    "messages": [response],
                    "workflow_continuation": False,
                }
        except Exception as exc:
            self._owner.logger.error(
                "[FORCE] Fallback response failed: %s", exc
            )
        return {
            "messages": [
                AIMessage(
                    content=_IN_CHARACTER_FALLBACK, tool_calls=[]
                )
            ],
            "workflow_continuation": False,
        }

    @staticmethod
    def _build_clean_history(
        all_messages: List[BaseMessage],
        user_question: str,
    ) -> List[BaseMessage]:
        """Return conversation history with tool calls/results stripped."""
        clean: List[BaseMessage] = []
        for msg in all_messages:
            cls = msg.__class__.__name__
            if cls == "ToolMessage":
                continue
            if cls == "AIMessage" and getattr(msg, "tool_calls", None):
                continue
            clean.append(msg)
        if not clean or clean[-1].__class__.__name__ != "HumanMessage":
            clean.append(HumanMessage(content=user_question))
        return clean

    # ------------------------------------------------------------------
    # Static utilities still referenced by other modules
    # ------------------------------------------------------------------

    @staticmethod
    def has_tool_calls(message: BaseMessage) -> bool:
        """Return whether one message contains tool calls."""
        return hasattr(message, "tool_calls") and bool(message.tool_calls)

    @staticmethod
    def get_user_question(messages: List[BaseMessage]) -> str:
        """Return the most recent human message content."""
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                content = msg.content
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    for block in content:
                        if (
                            isinstance(block, dict)
                            and block.get("type") == "text"
                        ):
                            return str(block.get("text", ""))
        return ""

    @staticmethod
    def get_tool_messages(messages: List[BaseMessage]) -> List[Any]:
        """Return ToolMessages from the current tool-call round only."""
        cutoff = 0
        for i, msg in enumerate(reversed(messages)):
            if (
                hasattr(msg, "tool_calls")
                and getattr(msg, "tool_calls", None)
            ):
                cutoff = len(messages) - i
                break
        return [
            msg
            for msg in messages[cutoff:]
            if msg.__class__.__name__ == "ToolMessage"
        ]

    @staticmethod
    def combine_tool_results(tool_messages: List[Any]) -> str:
        """Combine tool-result content into one context string."""
        parts: list[str] = []
        for index, tm in enumerate(tool_messages, start=1):
            content = getattr(tm, "content", "")
            if content:
                parts.append(
                    f"\n--- Tool Result {index} ---\n{content}\n"
                )
        return "".join(parts)

    def should_return_tool_direct(self, tool_name: str) -> bool:
        """Return whether one bound tool bypasses the model."""
        tools = getattr(self._owner, "_tools", []) or []
        for tool in tools:
            if getattr(tool, "name", None) == tool_name:
                return bool(getattr(tool, "return_direct", False))
        return False
