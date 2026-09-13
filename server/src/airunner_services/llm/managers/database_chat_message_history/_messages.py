"""Message CRUD: add, add multiple, clear, metadata retrieval.

Moved verbatim from the former monolithic
``database_chat_message_history.py`` module, except that the oversized
``add_message`` body was extracted into ``_prepare_message_dict``
(identical behavior, satisfies the pre-commit function-size limits).
"""

import datetime

from langchain_core.messages import AIMessage, BaseMessage

from airunner_services.database.models.conversation import Conversation


class DatabaseChatMessageCRUDMixin:
    """add_message / add_messages / clear / tool-metadata retrieval."""

    def add_message(self, message: BaseMessage) -> None:
        """Add a message to the conversation.

        Args:
            message: LangChain message to add
        """
        if self.ephemeral:
            self._ephemeral_messages.append(message)
            return

        if not self._conversation:
            self.logger.error("Cannot add message: no conversation loaded")
            return

        try:
            message_dict = self._prepare_message_dict(message)
            if message_dict is not None:
                self._persist_message_dict(
                    message_dict,
                    message_dict["role"],
                )

        except Exception:
            self.logger.exception("Error adding message")

    def _prepare_message_dict(
        self,
        message: BaseMessage,
    ) -> dict | None:
        """Build the persisted message dict for *message*.

        Returns ``None`` when the message was handled as a tool /
        internal / duplicate entry and must not be persisted as a
        regular message.
        """
        # Reload conversation from database to get latest state so
        # deduplication checks see the most current data.
        self._load_conversation()

        if self._try_handle_tool_message(message):
            return None
        if self._try_handle_ai_tool_calls(message):
            return None
        if self._is_internal_context(message):
            return None

        role, name = self._resolve_message_role(message)
        pending_model, pending_docs = self._consume_pending_metadata(
            message,
        )

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        content = message.content
        thinking_content: str | None = None

        if isinstance(message, AIMessage):
            content, thinking_content = self._extract_ai_thinking(
                message,
                content,
            )

        if self._is_duplicate_message(content, role):
            return None

        return self._build_message_dict(
            role=role,
            name=name,
            content=content,
            now=now,
            thinking_content=thinking_content,
            pending_model=pending_model,
            pending_docs=pending_docs,
            message=message,
        )

    def add_messages(self, messages: list[BaseMessage]) -> None:
        """Add multiple messages to the conversation.

        Args:
            messages: List of LangChain messages to add
        """
        for message in messages:
            self.add_message(message)

    def clear(self) -> None:
        """Clear all messages from the conversation."""
        if not self._conversation:
            return

        try:
            self._conversation.value = []
            Conversation.objects.update(self.conversation_id, value=[])
            self.logger.info("Cleared conversation %s", self.conversation_id)

        except Exception:
            self.logger.exception("Error clearing conversation")

    def get_tool_call_metadata(self) -> list[dict]:
        """Retrieve tool call metadata for debugging.

        Returns:
            List of dicts containing tool call requests and results
        """
        if not self._conversation:
            return []

        try:
            # Refresh conversation from database
            self._conversation = Conversation.objects.get(self.conversation_id)
            conversation_value = self._conversation.value or []

            # Extract only metadata entries
            metadata = []
            for msg in conversation_value:
                if not isinstance(msg, dict):
                    continue
                if msg.get("metadata_type") in (
                    "tool_calls",
                    "tool_result",
                ):
                    metadata.append(msg)

            return metadata

        except Exception:
            self.logger.exception("Error retrieving tool call metadata")
            return []
