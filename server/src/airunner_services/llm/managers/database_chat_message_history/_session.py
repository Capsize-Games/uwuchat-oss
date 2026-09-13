"""Conversation session lifecycle: load, create, rollback.

Moved verbatim from the former monolithic
``database_chat_message_history.py`` module.
"""

from airunner_services.database.models.conversation import Conversation


class DatabaseChatMessageSessionMixin:
    """Conversation loading/creation and orphan-message rollback."""

    def _load_conversation(self) -> None:
        """Load the conversation from database or create a new one."""
        try:
            if self.conversation_id:
                # Load specific conversation
                self._conversation = Conversation.objects.get(self.conversation_id)
            else:
                self._conversation = self._get_or_create_conversation()

            if self._conversation:
                self.conversation_id = self._conversation.id
                self.logger.info(f"Loaded conversation ID: {self.conversation_id}")
            else:
                self.logger.warning("Failed to load or create conversation")

        except Exception as e:
            # DataEncryptionError means the user's DEK cache expired —
            # silently swallowing it would hide the problem from the
            # RPC error handler, so the client never forces re-auth.
            from airunner_services.utils.crypto.data_encryption import (
                DataEncryptionError,
            )

            if isinstance(e, DataEncryptionError):
                raise
            self.logger.exception("Error loading conversation")

    def _get_or_create_conversation(self):
        """Load the current conversation or create a new one."""
        conversations = Conversation.objects.filter_by(current=True)
        if conversations:
            return conversations[0]
        conversation = Conversation.create()
        if conversation:
            self.conversation_id = conversation.id
            Conversation.make_current(self.conversation_id)
        return conversation

    def add_metadata_entry(self, entry: dict) -> None:
        """Append a metadata entry to the conversation and persist it.

        Follows the same append-and-persist pattern used internally by
        ``add_message()`` for ``tool_calls`` and ``tool_result``
        entries.  Callers should set ``metadata_type`` on *entry* so
        the ``messages`` property filters it from LLM context.
        """
        if self._conversation is None:
            return
        if self._conversation.value is None:
            self._conversation.value = []
        self._conversation.value.append(entry)
        Conversation.objects.update(
            self.conversation_id,
            value=self._conversation.value,
        )

    def trim_orphaned_user_message(self) -> None:
        """Remove a trailing user message with no assistant response.

        Public entry point for callers that detect a failed reply and
        need to roll back the already-persisted user turn.  Safe to
        call when there is no orphaned message — does nothing.
        """
        self._load_conversation()
        self._trim_orphaned_user_message()

    def _trim_orphaned_user_message(self) -> None:
        """Remove a trailing user message with no assistant response."""
        if not self._conversation:
            return
        value = self._conversation.value
        if not isinstance(value, list) or not value:
            return
        for i in range(len(value) - 1, -1, -1):
            msg = value[i]
            if not isinstance(msg, dict):
                continue
            if self._is_metadata_entry(msg):
                continue
            if msg.get("role") == "user":
                self.logger.info(
                    "Trimming orphaned user message from " "conversation %s",
                    self.conversation_id,
                )
                value.pop(i)
                Conversation.objects.update(
                    self.conversation_id,
                    value=value,
                )
            break
