"""Service-owned conversation history loader and formatter."""

from typing import Any, Dict, List, Optional

from airunner_services.data.tenant import get_account_id
from airunner_services.database.models.conversation import Conversation
from airunner_services.database.models.user import User
from airunner_services.settings import AIRUNNER_LOG_LEVEL
from airunner_services.utils.application import get_logger

from .conversation_summary_helpers import (
    format_conversation_payload,
    load_history,
    resolve_conversation_summary,
)

_METADATA_TYPES = frozenset({"tool_calls", "tool_result", "rag_injection"})

_logger = get_logger(__name__, AIRUNNER_LOG_LEVEL)


def trim_orphaned_user_message(conversation: Conversation) -> bool:
    """Remove a trailing user message with no assistant response.

    Returns True if a message was removed and persisted.
    """
    value = conversation.value
    if not isinstance(value, list) or not value:
        return False
    for i in range(len(value) - 1, -1, -1):
        msg = value[i]
        if not isinstance(msg, dict):
            continue
        if msg.get("metadata_type") in _METADATA_TYPES:
            continue
        if msg.get("role") == "user":
            _logger.info(
                "Trimming orphaned user message from conversation %s",
                conversation.id,
            )
            value.pop(i)
            Conversation.objects.update(conversation.id, value=value)
            return True
        break
    return False


class ConversationHistoryManager:
    """Handles fetching and formatting of conversation history."""

    def __init__(self) -> None:
        """Initialize one conversation history manager."""
        self.logger = get_logger(__name__, AIRUNNER_LOG_LEVEL)

    def get_current_conversation(self) -> Optional[Conversation]:
        """Fetch the current conversation if one exists."""
        conversations = Conversation.objects.filter_by(current=True)
        if len(conversations) == 0:
            self.logger.info("No current conversation found.")
            return None
        self.logger.debug("Fetching the current conversation.")
        try:
            conversation = conversations[0]
            if conversation:
                self.logger.debug(
                    f"Current conversation ID: {conversation.id}"
                )
                return conversation
            self.logger.info("No current conversation found.")
            return None
        except Exception as exc:
            self.logger.error(
                f"Error fetching current conversation: {exc}",
                exc_info=True,
            )
            return None

    def get_most_recent_conversation_id(self) -> Optional[int]:
        """Fetch the most recent conversation id if one exists."""
        self.logger.debug("Fetching the most recent conversation ID.")
        try:
            conversation = Conversation.most_recent()
            if conversation:
                self.logger.info(
                    f"Most recent conversation ID: {conversation.id}"
                )
                return conversation.id
            self.logger.info("No conversations found.")
            return None
        except Exception as exc:
            self.logger.error(
                f"Error fetching most recent conversation ID: {exc}",
                exc_info=True,
            )
            return None

    def list_conversations(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return serialized conversation metadata for service consumers."""
        conversations = Conversation.objects.filter(Conversation.id >= 1) or []
        ordered = sorted(
            conversations,
            key=lambda item: getattr(item, "updated_at", None)
            or getattr(item, "id", 0),
            reverse=True,
        )
        if limit > 0:
            ordered = ordered[:limit]
        summary = resolve_conversation_summary
        return [
            format_conversation_payload(item, summary(item, self.logger))
            for item in ordered
        ]

    def get_conversation_session(
        self,
        conversation_id: Optional[int] = None,
        max_messages: int = 50,
        mark_current: bool = False,
    ) -> Dict[str, Any]:
        """Return one serialized conversation plus formatted messages."""
        conversation = self._resolve_conversation(conversation_id)
        if conversation is None:
            return {
                "conversation": None,
                "conversation_id": None,
                "messages": [],
            }

        if mark_current:
            Conversation.make_current(conversation.id)

        # Clean up orphaned user messages that have no assistant response.
        # This can happen when an error occurs after the user message is
        # persisted but before the LLM response is stored.
        trim_orphaned_user_message(conversation)

        messages = self.load_conversation_history(
            conversation=conversation,
            max_messages=max_messages,
        )
        summary = resolve_conversation_summary(conversation, self.logger)
        current_mood = (conversation.user_data or {}).get(
            "current_mood"
        ) or {}
        # Fallback: when user_data is missing the current mood (e.g.
        # intra-session mood was not persisted before the turn completed),
        # scan the last assistant message for bot_mood fields.
        if not current_mood and messages:
            for msg in reversed(messages):
                if (
                    isinstance(msg, dict)
                    and msg.get("role") == "assistant"
                    and msg.get("bot_mood")
                    and msg.get("bot_mood") != "neutral"
                ):
                    current_mood = {
                        "mood": msg["bot_mood"],
                        "emoji": msg.get("bot_mood_emoji", "😐"),
                        "kaomoji": msg.get("bot_mood_kaomoji")
                        or "(｡◕ᴗ◕｡)",
                    }
                    break
        self.logger.warning(
            "[MOOD DEBUG] get_conversation_session conv_id=%s "
            "user_data=%r current_mood=%r",
            conversation.id, conversation.user_data, current_mood,
        )
        return {
            "conversation": format_conversation_payload(conversation, summary),
            "conversation_id": conversation.id,
            "messages": messages,
            "current_mood": current_mood,
        }

    def summarize_conversation(
        self,
        conversation_id: int,
    ) -> Optional[Dict[str, Any]]:
        """Return one persisted or generated summary for a conversation."""
        conversation = self._conversation_by_id(conversation_id)
        if conversation is None:
            return None
        return {
            "conversation_id": conversation_id,
            "summary": resolve_conversation_summary(conversation, self.logger),
        }

    @staticmethod
    def _current_tenant_user() -> Optional[User]:
        """Return (lazily creating) the authenticated account's User row.

        ``Conversation.create()`` falls back to ``User.objects.first()``
        when no user is given — a desktop-app-era convenience that
        silently attributes every new conversation to whichever user
        row happens to be oldest in the tenant schema, regardless of
        who is actually authenticated. Resolving explicitly here (by
        the ``users.id == account_id`` convention already used by
        ``headlesscode_service.create_project``) keeps ownership
        correct for tenants that end up with more than one user row.
        """
        account_id = get_account_id()
        if account_id is None:
            return None
        user = User.objects.get(account_id)
        if user is not None:
            return user
        return User.objects.create(
            id=account_id, username=f"user_{account_id}",
        )

    def create_conversation(
        self,
        max_messages: int = 50,
    ) -> Dict[str, Any]:
        """Create one new current conversation and return its session."""
        conversation = Conversation.create(user=self._current_tenant_user())
        if conversation is None or getattr(conversation, "id", None) is None:
            return {
                "conversation": None,
                "conversation_id": None,
                "messages": [],
            }
        return self.get_conversation_session(
            conversation_id=conversation.id,
            max_messages=max_messages,
            mark_current=True,
        )

    def delete_conversation(self, conversation_id: int) -> bool:
        """Delete one conversation from persistent storage."""
        conversation = self._conversation_by_id(conversation_id)
        if conversation is None:
            return False
        Conversation.delete(conversation_id)
        return True

    def delete_all_conversations(self) -> int:
        """Delete all conversations from persistent storage."""
        return int(Conversation.objects.delete_all() or 0)

    def update_conversation_messages(
        self,
        conversation_id: int,
        messages: List[Dict[str, Any]],
    ) -> bool:
        """Persist one conversation's messages."""
        if self._conversation_by_id(conversation_id) is None:
            return False
        Conversation.objects.update(pk=conversation_id, value=list(messages))
        return True

    def update_conversation_user_data(
        self,
        conversation_id: int,
        user_data: Dict[str, Any],
    ) -> bool:
        """Persist one conversation's user-data payload."""
        if self._conversation_by_id(conversation_id) is None:
            return False
        Conversation.objects.update(
            pk=conversation_id,
            user_data=dict(user_data or {}),
        )
        return True

    def _resolve_conversation(
        self,
        conversation_id: Optional[int],
    ) -> Optional[Conversation]:
        """Resolve one conversation by id or current/most-recent fallback."""
        if conversation_id is not None:
            return self._conversation_by_id(conversation_id)

        current = self.get_current_conversation()
        if current is not None:
            return current
        return Conversation.most_recent()

    @staticmethod
    def _conversation_by_id(
        conversation_id: int,
    ) -> Optional[Conversation]:
        """Return one conversation by primary key."""
        return Conversation.objects.filter_by_first(id=conversation_id)

    def load_conversation_history(
        self,
        conversation: Optional[Conversation] = None,
        conversation_id: Optional[int] = None,
        max_messages: int = 50,
    ) -> List[Dict[str, Any]]:
        """Load and format one conversation history for display."""
        if conversation is None and conversation_id is not None:
            conversation = Conversation.objects.filter_by_first(
                id=conversation_id
            )
            if conversation is None:
                self.logger.warning(
                    f"Conversation {conversation_id} not found."
                )
                return []
        elif conversation is None:
            conversation = self.get_current_conversation()

        if conversation is None:
            conversation = Conversation.most_recent()
            if conversation is None:
                self.logger.warning(
                    "No conversation found. Returning empty history."
                )
                return []
        return load_history(conversation, self.logger, max_messages)
