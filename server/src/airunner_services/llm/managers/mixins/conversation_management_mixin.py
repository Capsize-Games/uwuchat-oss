"""Conversation management mixin for LLM model manager.

This mixin handles conversation lifecycle operations including creating,
loading, clearing, and managing conversation history in the database.
"""

import logging
from typing import TYPE_CHECKING, Dict, Optional

from airunner_services.database.models.conversation import Conversation

if TYPE_CHECKING:
    from airunner_services.model_management.llm_model_manager import (
        LLMModelManager,
    )

logger = logging.getLogger(__name__)


class ConversationManagementMixin:
    """Mixin for managing conversation history and state.

    Handles conversation creation, loading, deletion, and integration
    with the workflow manager's memory system.
    """

    def on_conversation_deleted(self: "LLMModelManager", data: Dict) -> None:
        """Handle conversation deletion event.

        Clears workflow manager memory when a conversation is deleted.

        Args:
            data: Event data dictionary (not currently used).
        """
        if self._workflow_manager:
            self._workflow_manager.clear_memory()

    def clear_history(
        self: "LLMModelManager", data: Optional[Dict] = None
    ) -> None:
        """Clear chat history and start a new conversation.

        Creates or retrieves a conversation and sets it as current,
        then updates the workflow manager with the new conversation ID.

        Args:
            data: Optional dict with conversation_id key.
        """
        data = data or {}
        conversation = self._get_or_create_conversation(data)

        if conversation:
            self._set_conversation_as_current(conversation)

        self._update_workflow_with_conversation(conversation)

    def _set_conversation_as_current(
        self: "LLMModelManager", conversation: Conversation
    ) -> None:
        """Set conversation as the current active conversation.

        Args:
            conversation: Conversation object to set as current.
        """
        Conversation.make_current(conversation.id)
        self.logger.info(
            f"Starting new conversation with ID: {conversation.id}"
        )

    def _update_workflow_with_conversation(
        self: "LLMModelManager",
        conversation: Optional[Conversation],
        ephemeral: bool = False,
    ) -> None:
        """Update workflow manager with conversation ID or clear memory.

        Args:
            conversation: Conversation object, or None to clear memory.
            ephemeral: If True, don't save conversation to database (memory-only).
        """
        if not self._workflow_manager:
            return

        if conversation:
            if ephemeral:
                self._workflow_manager.set_conversation_id(
                    conversation.id,
                    ephemeral=True,
                )
            else:
                self._workflow_manager.set_conversation_id(conversation.id)
        else:
            self._workflow_manager.clear_memory()

    def _get_or_create_conversation(
        self: "LLMModelManager", data: Dict
    ) -> Optional[Conversation]:
        """Get existing conversation or create a new one.

        Args:
            data: Dict that may contain conversation_id and chatbot_id keys.

        Returns:
            Conversation object, or None if creation/retrieval failed.
        """
        conversation_id = data.get("conversation_id")
        chatbot_id = data.get("chatbot_id")
        if conversation_id:
            return self._load_existing_conversation(
                conversation_id, chatbot_id=chatbot_id
            )

        # UwUChat convention: pass the chat session UUID in node_id.
        # Reuse or create a Conversation keyed by that identifier so
        # history attaches to the same record.
        node_id = data.get("node_id")
        if isinstance(node_id, str):
            key = node_id.strip()
            if key:
                try:
                    existing = Conversation.objects.filter_by_first(key=key)
                except Exception:
                    existing = None
                if existing:
                    try:
                        data["conversation_id"] = existing.id
                    except Exception:
                        pass
                    return existing

                conversation = self._create_new_conversation(data)
                if conversation:
                    try:
                        Conversation.objects.update(conversation.id, key=key)
                        conversation.key = key
                    except Exception:
                        pass
                return conversation

        return self._create_new_conversation(data)

    def _create_new_conversation(
        self: "LLMModelManager", data: Dict
    ) -> Optional[Conversation]:
        """Create a new conversation and update settings.

        When ``data["chatbot_id"]`` is present (the normal case after
        round-1/2 WS payload plumbing), the Chatbot row is looked up and
        passed explicitly to ``Conversation.create()``.  This prevents a
        brand-new persona's first message from being silently attached to
        the most-recently-active chatbot via the global fallback in
        ``Conversation.create()``.

        Args:
            data: Dict to update with new conversation_id.  May include
                ``chatbot_id``.

        Returns:
            New Conversation object, or None if creation failed.
        """
        chatbot = None
        chatbot_id = data.get("chatbot_id")
        if chatbot_id is not None:
            try:
                from airunner_services.database.models.chatbot import Chatbot
                chatbot = Chatbot.objects.get(int(chatbot_id))
                if chatbot and getattr(chatbot, "deleted", False):
                    chatbot = None
            except Exception:
                logger.warning(
                    "Chatbot lookup failed for chatbot_id=%s, "
                    "falling back to Conversation.create() default",
                    chatbot_id,
                )

        conversation = Conversation.create(chatbot=chatbot)

        if not conversation:
            return None

        # Resolve the current session so mood updates and session-end
        # tasks (summarization, memory, curiosity) have a session to
        # attach to.  Conversations created without a session_id
        # silently skip every session-dependent background feature.
        try:
            from airunner_services.llm.session_manager import (
                SessionManager,
            )
            user_id = data.get("user_id")
            manager = SessionManager()
            session, _conv, _cold, _gap = manager.get_or_create_session(
                int(chatbot_id),
                int(user_id) if user_id else None,
            )
            if session:
                Conversation.objects.update(
                    conversation.id, session_id=session.id,
                )
                conversation.session_id = session.id
        except Exception:
            logger.warning(
                "Failed to resolve session for new conversation %s",
                conversation.id,
                exc_info=True,
            )

        data["conversation_id"] = conversation.id
        self.update_llm_generator_settings(
            current_conversation_id=conversation.id
        )
        return conversation

    def _load_existing_conversation(
        self: "LLMModelManager",
        conversation_id: int,
        chatbot_id: Optional[int] = None,
    ) -> Optional[Conversation]:
        """Load an existing conversation by ID.

        When *chatbot_id* is supplied the loaded conversation's
        ``chatbot_id`` is cross-checked.  A mismatch indicates the
        client sent a stale ``conversation_id`` from a different
        chatbot (e.g. a mid-switch race) — the message is rejected so
        the error surfaces on the client rather than silently mis-filing.

        Args:
            conversation_id: Database ID of conversation to load.
            chatbot_id: Optional expected chatbot ID for validation.

        Returns:
            Conversation object, or None if not found or mismatched.

        Raises:
            ValueError: When chatbot_id is provided and does not match
                the loaded conversation's chatbot_id.
        """
        conversation = Conversation.objects.get(conversation_id)

        if conversation and chatbot_id is not None:
            conv_chatbot_id = getattr(conversation, "chatbot_id", None)
            if conv_chatbot_id is not None and conv_chatbot_id != chatbot_id:
                logger.warning(
                    "conversation %s chatbot_id %s != request chatbot_id %s "
                    "— rejecting to prevent cross-chatbot message leak",
                    conversation_id,
                    conv_chatbot_id,
                    chatbot_id,
                )
                raise ValueError(
                    "Conversation belongs to a different chatbot"
                )

        if conversation:
            self.update_llm_generator_settings(
                current_conversation_id=conversation_id
            )

        return conversation

    def add_chatbot_response_to_history(
        self: "LLMModelManager", message: str
    ) -> None:
        """Add a chatbot-generated response to chat history.

        Currently a no-op placeholder for future implementation.

        Args:
            message: The chatbot's response message.
        """

    def load_conversation(self: "LLMModelManager", message: Dict) -> None:
        """Load an existing conversation into the chat workflow.

        If workflow manager is loaded, sets the conversation ID immediately.
        Otherwise, stores message as pending for later processing.

        Ownership check: the target conversation must belong to the
        current chatbot (or, when no chatbot is set, the current user).
        Rejects cross-chatbot / cross-user loads with a warning log.

        Args:
            message: Dict containing conversation_id key.
        """
        conversation_id = message.get("conversation_id")
        if conversation_id is None:
            return

        if not self._conversation_belongs_to_current_context(
            conversation_id
        ):
            return

        if self._workflow_manager is not None:
            self._load_conversation_into_workflow(conversation_id)
            self._pending_conversation_message = None
        else:
            self._defer_conversation_load(conversation_id, message)

    def _conversation_belongs_to_current_context(
        self: "LLMModelManager", conversation_id: int,
    ) -> bool:
        """Return True when *conversation_id* is scoped to the current
        chatbot or user (reject cross-tenant loads)."""
        try:
            conv = Conversation.objects.get(conversation_id)
        except Exception:
            self.logger.warning(
                "load_conversation: lookup failed for %s", conversation_id,
            )
            return False
        if conv is None:
            self.logger.warning(
                "load_conversation: conversation %s not found",
                conversation_id,
            )
            return False

        chatbot = getattr(self, "chatbot", None)
        if chatbot is not None:
            conv_chatbot_id = getattr(conv, "chatbot_id", None)
            if conv_chatbot_id is None:
                self.logger.warning(
                    "load_conversation: conversation %s has no "
                    "chatbot_id — cannot verify ownership, rejected",
                    conversation_id,
                )
                return False
            if conv_chatbot_id != chatbot.id:
                self.logger.warning(
                    "load_conversation: conversation %s belongs to "
                    "chatbot %s, not current chatbot %s — rejected",
                    conversation_id,
                    conv_chatbot_id,
                    chatbot.id,
                )
                return False
            return True

        # No chatbot set — fall back to user-level check via the
        # currently-loaded workflow conversation.
        wm = getattr(self, "_workflow_manager", None)
        active_conv_id = (
            getattr(wm, "_conversation_id", None) if wm else None
        )
        if active_conv_id is not None:
            try:
                active_conv = Conversation.objects.get(active_conv_id)
            except Exception:
                active_conv = None
            if active_conv is not None:
                active_user_id = getattr(active_conv, "user_id", None)
                target_user_id = getattr(conv, "user_id", None)
                if active_user_id is None or target_user_id is None:
                    self.logger.warning(
                        "load_conversation: cannot verify ownership "
                        "of conversation %s — active_user_id=%s "
                        "target_user_id=%s — rejected",
                        conversation_id,
                        active_user_id,
                        target_user_id,
                    )
                    return False
                if active_user_id != target_user_id:
                    self.logger.warning(
                        "load_conversation: conversation %s belongs to "
                        "user %s, not current user %s — rejected",
                        conversation_id,
                        target_user_id,
                        active_user_id,
                    )
                    return False
                return True

        self.logger.warning(
            "load_conversation: no current context available to "
            "verify ownership of conversation %s — rejected",
            conversation_id,
        )
        return False

    def _load_conversation_into_workflow(
        self: "LLMModelManager", conversation_id: Optional[int]
    ) -> None:
        """Load conversation into the workflow manager.

        Args:
            conversation_id: ID of conversation to load, or None.
        """
        if conversation_id and hasattr(
            self._workflow_manager, "set_conversation_id"
        ):
            self._workflow_manager.set_conversation_id(conversation_id)
            self.logger.info(
                f"Updated workflow manager with conversation ID: "
                f"{conversation_id}"
            )
        else:
            self.logger.info(
                f"Workflow manager loaded. Conversation {conversation_id} "
                "context available."
            )

    def _defer_conversation_load(
        self: "LLMModelManager", conversation_id: Optional[int], message: Dict
    ) -> None:
        """Defer conversation loading until workflow manager is ready.

        Args:
            conversation_id: ID of conversation to load.
            message: Original message dict to process later.
        """
        self.logger.warning(
            f"Workflow manager not loaded. Will use "
            f"ConversationHistoryManager for conversation ID: {conversation_id}."
        )
        self._pending_conversation_message = message

    def reload_rag_engine(self: "LLMModelManager") -> None:
        """Reload the Retrieval-Augmented Generation engine.

        Unloads and reloads the tool manager, then updates workflow
        manager with refreshed tools.
        """
        if not self._tool_manager:
            self.logger.warning("Cannot reload RAG - tool manager not loaded")
            return

        self._reload_tool_manager()
        self._update_workflow_tools()

    def _reload_tool_manager(self: "LLMModelManager") -> None:
        """Unload and reload the tool manager."""
        self._unload_tool_manager()
        self._load_tool_manager()

    def _update_workflow_tools(self: "LLMModelManager") -> None:
        """Update workflow manager with refreshed tools."""
        if self._workflow_manager:
            self._workflow_manager._tool_manager = self._tool_manager
            self._workflow_manager.update_tools(self.tools)
