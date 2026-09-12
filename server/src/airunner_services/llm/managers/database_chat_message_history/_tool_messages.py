"""Tool-call / tool-result metadata persistence (add_message path).

Moved verbatim from the former monolithic
``database_chat_message_history.py`` module.
"""

import datetime

from langchain_core.messages import AIMessage, BaseMessage

from airunner_services.database.models.conversation import Conversation
from airunner_services.llm.thinking_parser import (
    extract_thinking_and_response,
    normalize_thinking_content,
)
from airunner_services.llm.tool_call_identity import tool_call_identity_set

from ._format import _friendly_tool_status
from ._sync import _record_tool_call, _record_tool_result


class DatabaseChatToolMessageMixin:
    """ToolMessage and AIMessage(tool_calls) persistence helpers."""

    def _try_handle_tool_message(self, message: BaseMessage) -> bool:
        """Handle ToolMessage storage. Returns True if the message was
        a ToolMessage and has been persisted (or deduplicated)."""
        if message.__class__.__name__ != "ToolMessage":
            return False
        tool_call_id = getattr(message, "tool_call_id", None)
        content_len = len(message.content) if message.content else 0
        self.logger.debug(
            "Tool result: content_len=%d tool_call_id=%s",
            content_len,
            tool_call_id or "unknown",
        )
        if self._tool_result_exists(tool_call_id):
            return True
        self._persist_tool_result(message, tool_call_id)
        return True

    def _tool_result_exists(self, tool_call_id: str | None) -> bool:
        """Return True when a tool_result with *tool_call_id* already
        exists in the conversation value."""
        if not self._conversation.value or not tool_call_id:
            return False
        for existing in self._conversation.value:
            if not isinstance(existing, dict):
                continue
            if (
                existing.get("metadata_type") == "tool_result"
                and existing.get("tool_call_id") == tool_call_id
            ):
                self.logger.debug(
                    "Skipping duplicate tool_result for " "tool_call_id: %s",
                    tool_call_id,
                )
                return True
        return False

    def _persist_tool_result(
        self,
        message: "BaseMessage",
        tool_call_id: str,
    ) -> None:
        """Persist a ToolMessage as a tool_result metadata entry."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        tool_result_dict = {
            "role": "tool_result",
            "name": "Tool Result",
            "content": message.content,
            "timestamp": now,
            "blocks": [{"block_type": "text", "text": message.content}],
            "tool_call_id": tool_call_id,
            "metadata_type": "tool_result",
        }
        if self.call_chain_id:
            tool_result_dict["call_chain_id"] = self.call_chain_id
        if self._conversation.value is None:
            self._conversation.value = []
        self._conversation.value.append(tool_result_dict)
        Conversation.objects.update(
            self.conversation_id,
            value=self._conversation.value,
        )
        _record_tool_result(self._conversation, tool_result_dict)

    def _try_handle_ai_tool_calls(self, message: BaseMessage) -> bool:
        """Handle an AIMessage that requests tool calls.
        Returns True if the message was handled (persisted or deduped)."""
        if not (
            isinstance(message, AIMessage)
            and hasattr(message, "tool_calls")
            and message.tool_calls
        ):
            return False
        self.logger.debug(
            "Tool calls requested: %s",
            [tc.get("name", "unknown") for tc in message.tool_calls],
        )
        if self._tool_calls_exist(message.tool_calls):
            return True
        thinking_content = self._extract_pre_tool_thinking(message)
        self._persist_tool_calls(message, thinking_content)
        return True

    def _tool_calls_exist(self, tool_calls: list) -> bool:
        """Return True when tool_calls with overlapping IDs or canonical
        identities already exist in the conversation value."""
        incoming_tool_ids = {tc.get("id") for tc in tool_calls if tc.get("id")}
        incoming_identities = tool_call_identity_set(tool_calls)
        if not self._conversation.value or (
            not incoming_tool_ids and not incoming_identities
        ):
            return False
        for existing in self._conversation.value:
            if not isinstance(existing, dict):
                continue
            if existing.get("metadata_type") != "tool_calls":
                continue
            existing_calls = existing.get("tool_calls", [])
            existing_tool_ids = {tc.get("id") for tc in existing_calls if tc.get("id")}
            if incoming_tool_ids.intersection(existing_tool_ids):
                self.logger.debug(
                    "Skipping duplicate tool_calls — " "tool_call_id already exists",
                )
                return True
            existing_identities = tool_call_identity_set(existing_calls)
            if incoming_identities.intersection(existing_identities):
                self.logger.debug(
                    "Skipping duplicate tool_calls — canonical "
                    "tool identity already exists",
                )
                return True
        return False

    def _extract_pre_tool_thinking(
        self,
        message: AIMessage,
    ) -> str | None:
        """Extract thinking content from an AIMessage that carries
        tool_calls (the "thinking before tool use" phase)."""
        thinking_content: str | None = None
        if hasattr(message, "additional_kwargs") and message.additional_kwargs:
            thinking_content = normalize_thinking_content(
                message.additional_kwargs.get("thinking_content")
                or message.additional_kwargs.get("reasoning_content"),
            )
        if not thinking_content and message.content:
            thinking_content, _ = extract_thinking_and_response(
                message.content,
            )
            thinking_content = normalize_thinking_content(thinking_content)
        return thinking_content

    def _persist_tool_calls(
        self,
        message: AIMessage,
        thinking_content: str | None,
    ) -> None:
        """Persist a tool_calls metadata entry for an AIMessage that
        requested tool execution."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        tool_names = [tc.get("name", "unknown") for tc in message.tool_calls]
        user_facing = _friendly_tool_status(tool_names)
        tool_calls_dict = {
            "role": "tool_calls",
            "name": "Tool Planning",
            "content": user_facing,
            "timestamp": now,
            "blocks": [
                {
                    "block_type": "text",
                    "text": f"Tool calls: {message.tool_calls}",
                }
            ],
            "tool_calls": message.tool_calls,
            "metadata_type": "tool_calls",
        }
        if self.call_chain_id:
            tool_calls_dict["call_chain_id"] = self.call_chain_id
        if thinking_content:
            tool_calls_dict["thinking_content"] = thinking_content
            self.logger.debug(
                "[THINKING SAVE] Saved pre-tool thinking: %d chars",
                len(thinking_content),
            )
        if self._conversation.value is None:
            self._conversation.value = []
        self._conversation.value.append(tool_calls_dict)
        Conversation.objects.update(
            self.conversation_id,
            value=self._conversation.value,
        )
        _record_tool_call(self._conversation, tool_calls_dict)
