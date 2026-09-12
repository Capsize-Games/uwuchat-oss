"""Message-dict construction and persistence helpers.

Moved verbatim from the former monolithic
``database_chat_message_history.py`` module.
"""

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)

from airunner_services.database.models.conversation import Conversation
from airunner_services.llm.thinking_parser import (
    extract_thinking_and_response,
    normalize_thinking_content,
    strip_stored_thinking_prefix,
)

from ._sync import _record_message_append


class DatabaseChatMessageBuildMixin:
    """Build and persist conversation message dicts."""

    def _resolve_message_role(
        self,
        message: BaseMessage,
    ) -> tuple[str, str]:
        """Resolve (role, display_name) from a LangChain message."""
        if isinstance(message, HumanMessage):
            return "user", getattr(
                self._conversation,
                "user_name",
                "User",
            )
        if isinstance(message, AIMessage):
            return "assistant", getattr(
                self._conversation,
                "chatbot_name",
                "Assistant",
            )
        if isinstance(message, SystemMessage):
            return "system", "System"
        return "user", "User"

    def _consume_pending_metadata(
        self,
        message: BaseMessage,
    ) -> tuple[str | None, list[str]]:
        """Consume pending model + document metadata from user_data.

        Returns (pending_model, pending_docs).  Persists the cleared
        user_data when there was metadata to consume.
        """
        if not isinstance(message, HumanMessage) or not self._conversation:
            return None, []
        user_data = self._conversation.user_data or {}
        pending_model: str | None = user_data.pop(
            "_pending_model",
            None,
        )
        pending_docs = list(
            user_data.pop("_pending_active_documents", []),
        )
        if pending_model or pending_docs:
            Conversation.objects.update(
                self.conversation_id,
                user_data=user_data,
            )
        return pending_model, pending_docs

    def _extract_ai_thinking(
        self,
        message: AIMessage,
        content: str,
    ) -> tuple[str, str | None]:
        """Extract thinking content from an AI message.

        Returns (cleaned_content, thinking_content).  Checks
        additional_kwargs first (streaming path), then falls back to
        extracting from the content string.
        """
        thinking: str | None = None
        if hasattr(message, "additional_kwargs") and message.additional_kwargs:
            thinking = normalize_thinking_content(
                message.additional_kwargs.get("thinking_content")
                or message.additional_kwargs.get("reasoning_content"),
            )
            self.logger.debug(
                "[THINKING SAVE] Found thinking_content in " "additional_kwargs: %s",
                bool(thinking),
            )
        if not thinking:
            thinking, content = extract_thinking_and_response(content)
            thinking = normalize_thinking_content(thinking)
            self.logger.debug(
                "[THINKING SAVE] Extracted from content: %s",
                bool(thinking),
            )
        content = strip_stored_thinking_prefix(content, thinking)
        self.logger.debug(
            "[THINKING SAVE] Final thinking_content length: %d",
            len(thinking) if thinking else 0,
        )
        return content, thinking

    def _is_duplicate_message(
        self,
        content: str,
        role: str,
    ) -> bool:
        """Return True when a message with the same role+content already
        exists as the latest message of that role."""
        if not self._conversation.value:
            return False
        for existing in reversed(self._conversation.value):
            if not isinstance(existing, dict):
                continue
            if existing.get("role") == role:
                if existing.get("content", "") == content:
                    self.logger.debug(
                        "Skipping duplicate %s message",
                        role,
                    )
                    return True
                break
        return False

    def _build_message_dict(
        self,
        role: str,
        name: str,
        content: str,
        now: str,
        thinking_content: str | None,
        pending_model: str | None,
        pending_docs: list[str],
        message: BaseMessage,
    ) -> dict:
        """Build the message dictionary with all metadata attached."""
        message_dict: dict = {
            "role": role,
            "name": name,
            "content": content,
            "timestamp": now,
            "blocks": [{"block_type": "text", "text": content}],
        }
        if pending_model:
            message_dict["model"] = pending_model
        if pending_docs:
            message_dict["active_documents"] = pending_docs
        self._attach_call_chain_id(message_dict, role)
        self._attach_bot_mood(message_dict, role)
        from airunner_services.llm.managers.mixins.tool_execution_mixin._event_stash import (
            attach_tool_events,
        )

        attach_tool_events(message_dict, role, self)
        if thinking_content:
            message_dict["thinking_content"] = thinking_content
        self._attach_safe_additional_kwargs(message_dict, message)
        return message_dict

    def _attach_call_chain_id(
        self,
        message_dict: dict,
        role: str,
    ) -> None:
        """Attach the active call-chain ID to assistant messages."""
        if role != "assistant":
            return
        cid = getattr(self, "_pending_call_chain_id", None)
        if not cid:
            try:
                from airunner_services.llm.active_call_chain import (
                    get_active_call_chain,
                )

                cid = get_active_call_chain()
            except ImportError:
                pass
        if cid:
            message_dict["call_chain_id"] = cid
            self._pending_call_chain_id = None

    def _attach_bot_mood(
        self,
        message_dict: dict,
        role: str,
    ) -> None:
        """Attach the pending bot mood payload to assistant messages."""
        if role != "assistant":
            return
        mood_payload = getattr(self, "_pending_bot_mood", None)
        if mood_payload:
            message_dict["bot_mood"] = mood_payload.get(
                "mood",
                "neutral",
            )
            message_dict["bot_mood_emoji"] = mood_payload.get(
                "emoji",
                "😐",
            )
            message_dict["bot_mood_kaomoji"] = mood_payload.get(
                "kaomoji",
                "(｡◕ᴗ◕｡)",
            )
            self._pending_bot_mood = None

    @staticmethod
    def _attach_safe_additional_kwargs(
        message_dict: dict,
        message: BaseMessage,
    ) -> None:
        """Attach additional_kwargs, stripping already-handled keys to
        prevent raw (un-normalized) values from leaking back in."""
        if not (hasattr(message, "additional_kwargs") and message.additional_kwargs):
            return
        safe_kwargs = {
            k: v
            for k, v in message.additional_kwargs.items()
            if k not in ("thinking_content", "reasoning_content")
        }
        message_dict.update(safe_kwargs)

    def _persist_message_dict(
        self,
        message_dict: dict,
        role: str,
    ) -> None:
        """Append *message_dict* to the conversation and persist to DB."""
        if self._conversation.value is None:
            self._conversation.value = []
        self._conversation.value.append(message_dict)
        result = Conversation.objects.update(
            self.conversation_id,
            value=self._conversation.value,
        )
        self.logger.debug(
            "[MSG PERSIST] conv=%d role=%s total_msgs=%d result=%s",
            self.conversation_id or -1,
            role,
            len(self._conversation.value),
            result,
        )
        _record_message_append(self._conversation, message_dict, role)
