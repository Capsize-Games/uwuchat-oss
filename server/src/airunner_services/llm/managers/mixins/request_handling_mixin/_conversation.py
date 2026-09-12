"""Request-time conversation preparation mixin.

Extracted from ``RequestHandlingMixin``.  Attaches the request to the
active conversation workflow state, syncs ``self.chatbot`` from the
conversation, and threads the resolved agent into the tool manager.
"""

from __future__ import annotations

from typing import Any, Dict


class RequestConversationMixin:
    """Conversation/agent preparation for incoming LLM requests."""

    def _prepare_request_memory(self, llm_request: Any) -> None:
        """Reset workflow memory when the request disables memory usage."""
        if not llm_request or getattr(llm_request, "use_memory", True):
            return

        self.logger.info(
            "use_memory=False - clearing conversation history for this "
            "request"
        )
        if self._workflow_manager:
            self._workflow_manager.clear_memory()

    def _prepare_request_conversation(
        self,
        data: Dict[str, Any],
        llm_request: Any,
    ) -> None:
        """Attach the request to the active conversation workflow state."""
        conversation = self._get_or_create_conversation(data)
        if not conversation:
            return

        self._sync_chatbot_from_conversation(conversation)

        ephemeral = bool(getattr(llm_request, "ephemeral_conversation", False))
        if hasattr(self, "_update_workflow_with_conversation"):
            self._update_workflow_with_conversation(
                conversation,
                ephemeral=ephemeral,
            )
            return

        if self._workflow_manager:
            self._workflow_manager.set_conversation_id(
                conversation.id,
                ephemeral=ephemeral,
            )

    def _sync_chatbot_from_conversation(self, conversation: Any) -> None:
        """Set self.chatbot from conversation when not already correct.

        The cloud path never pre-sets self.chatbot, so mood/social/knowledge
        context bindings would all target None (→ first DB row).  Resolving
        it here fixes every downstream binding in one place.
        """
        chatbot_id = getattr(conversation, "chatbot_id", None)
        if not chatbot_id:
            return
        current = getattr(self, "chatbot", None)
        if current and getattr(current, "id", None) == chatbot_id:
            return
        try:
            from airunner_services.database.models.chatbot import Chatbot
            chatbot = Chatbot.objects.get(chatbot_id)
        except Exception:
            self.logger.error(
                "_sync_chatbot_from_conversation failed — "
                "cannot resolve chatbot %s for conversation %s",
                chatbot_id,
                getattr(conversation, "id", None),
                exc_info=True,
            )
            return
        if not chatbot:
            return
        # Use _chatbot attr to bypass the read-only property
        self._chatbot = chatbot
        if getattr(self, "_workflow_manager", None):
            self._workflow_manager.chatbot = chatbot

    def _thread_agent_to_tool_manager(self) -> None:
        """Resolve the agent (chatbot + user) and pass it to ToolManager.

        Called after _prepare_request_conversation so self.chatbot is set.
        The agent object exposes .chatbot and .user, matching the contract
        expected by requires_agent tools (add_calendar_event, etc.).
        """
        if not self._tool_manager:
            return
        chatbot = getattr(self, "chatbot", None)
        if chatbot is None:
            return
        user = None
        try:
            from airunner_services.database.models.user import User

            wm = getattr(self, "_workflow_manager", None)
            conv_id = getattr(wm, "_conversation_id", None) if wm else None
            user_id = None
            if conv_id:
                from airunner_services.database.models.conversation \
                    import Conversation
                conv = Conversation.objects.get(conv_id)
                user_id = getattr(conv, "user_id", None) if conv else None
            if user_id:
                user = User.objects.get(user_id)
        except Exception:
            self.logger.warning(
                "Failed to resolve user for tool agent — "
                "requires_agent tools will receive agent=None"
            )
        from types import SimpleNamespace
        agent = SimpleNamespace(chatbot=chatbot, user=user)
        self._tool_manager.set_agent(agent)
