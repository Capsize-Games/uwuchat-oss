"""Base mixin: constructor, message read path and shared helpers.

Verbatim from the former monolithic module; the oversized
``messages`` property was decomposed into the private helpers
``_load_conversation_value`` / ``_convert_conversation_value`` /
``_message_from_dict`` (identical behavior).
"""

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from airunner_services.database.models.conversation import Conversation
from airunner_services.llm.gpt_oss_parser import (
    has_gpt_oss_markup,
    parse_gpt_oss_response,
)
from airunner_services.llm.thinking_parser import (
    normalize_thinking_content,
    strip_stored_thinking_prefix,
)
from airunner_services.utils.application.get_logger import get_logger


class DatabaseChatMessageHistoryBase:
    """Constructor and read path shared by the history mixins."""

    def __init__(
        self,
        conversation_id: int | None = None,
        ephemeral: bool = False,
        call_chain_id: str | None = None,
    ):
        """Initialize the database chat message history.

        Args:
            conversation_id: Optional conversation ID to load. If None,
                will use or create the current conversation.
            ephemeral: If True, messages stay in memory only.
            call_chain_id: Optional per-turn identifier attached to
                tool_calls / tool_result metadata entries.
        """
        self.logger = get_logger(self.__class__.__name__)
        self.conversation_id = conversation_id
        self.ephemeral = ephemeral
        self.call_chain_id = call_chain_id
        self._conversation = None
        self._ephemeral_messages = []  # In-memory storage for ephemeral mode
        # Completed tool results buffered during tool execution, attached
        # to the next assistant message dict by _attach_tool_events so
        # reloaded threads render tool-call widgets (see
        # ToolExecutionStatusMixin._stash_tool_event).
        self._pending_tool_events: list[dict] | None = None

        if not ephemeral:
            self._load_conversation()
            self._trim_orphaned_user_message()

    @staticmethod
    def _is_metadata_entry(msg: dict) -> bool:
        """Return True when *msg* is a metadata entry (not LLM input)."""
        return msg.get("metadata_type") in (
            "tool_calls",
            "tool_result",
            "rag_injection",
            "available_tools",
            "headlesscode_session",
        )

    @staticmethod
    def _reconstruct_tool_message(msg: dict) -> "BaseMessage | None":
        """Reconstruct a LangChain message from a tool metadata entry.

        Tool call evidence is stored as separate ``metadata_type``
        entries in ``Conversation.value``, but the LLM must see the
        original ``AIMessage(tool_calls=[...])`` → ``ToolMessage(...)``
        sequence to know a real tool call happened.  Without this
        reconstruction the model "forgets" it called a tool and may
        claim it fabricated its previous answer (amnesia bug).

        Returns ``None`` when *msg* is not a reconstructable tool
        metadata type (e.g. ``rag_injection``, ``available_tools``).
        """
        metadata_type = msg.get("metadata_type")
        if metadata_type == "tool_calls":
            return AIMessage(
                content=msg.get("content", ""),
                tool_calls=msg.get("tool_calls", []),
            )
        if metadata_type == "tool_result":
            return ToolMessage(
                content=msg.get("content", ""),
                tool_call_id=msg.get("tool_call_id", ""),
            )
        return None

    @property
    def messages(self) -> list[BaseMessage]:
        """Retrieve all messages from the conversation.

        Returns:
            List of LangChain BaseMessage objects (excludes tool call
            metadata)
        """
        # In ephemeral mode, return in-memory messages
        if self.ephemeral:
            return self._ephemeral_messages.copy()

        if not self._conversation:
            return []

        try:
            # Refresh conversation from database
            conversation_value = self._load_conversation_value()
            if conversation_value is None:
                return []
            return self._convert_conversation_value(conversation_value)

        except Exception:
            self.logger.exception("Error retrieving messages")
            return []

    def _load_conversation_value(self) -> list | None:
        """Refresh the conversation and return its raw value.

        Returns ``None`` when the stored value is not a list — this
        indicates a decryption failure and callers return an empty
        message list.
        """
        self._conversation = Conversation.objects.get(self.conversation_id)
        raw = self._conversation.value
        if not isinstance(raw, list):
            self.logger.error(
                "DatabaseChatMessageHistory: conversation %s "
                "returned non-list value (type=%s). This "
                "indicates a decryption failure — returning "
                "empty message list.",
                self.conversation_id,
                type(raw).__name__,
            )
            return None
        return raw

    def _convert_conversation_value(
        self,
        conversation_value: list[dict],
    ) -> list[BaseMessage]:
        """Convert database entries into LangChain messages."""
        langchain_messages: list[BaseMessage] = []
        for msg in conversation_value:
            if not isinstance(msg, dict):
                continue
            converted = self._message_from_dict(msg)
            if converted is not None:
                langchain_messages.append(converted)
        return langchain_messages

    def _message_from_dict(self, msg: dict) -> BaseMessage | None:
        """Build one LangChain message from a conversation entry.

        Returns ``None`` for non-reconstructable metadata entries
        (``rag_injection``, ``available_tools``) and unknown roles.
        """
        # Reconstruct tool_calls / tool_result metadata entries as real
        # LangChain objects so the LLM has evidence a tool was called
        # (tool-call history amnesia bug).
        if self._is_metadata_entry(msg):
            return self._reconstruct_tool_message(msg)

        role = msg.get("role", "user")
        content = msg.get("content", "")
        thinking_content = normalize_thinking_content(msg.get("thinking_content"))
        if has_gpt_oss_markup(content):
            parsed = parse_gpt_oss_response(content)
            content = parsed.content or content
            parsed_thinking = normalize_thinking_content(parsed.thinking_content)
            if parsed_thinking and not thinking_content:
                thinking_content = parsed_thinking
        content = strip_stored_thinking_prefix(
            content,
            thinking_content,
        )

        timestamp = msg.get("timestamp", "")
        if role == "user":
            return HumanMessage(
                content=content,
                additional_kwargs={"timestamp": timestamp},
            )
        if role in ("assistant", "bot"):
            additional_kwargs = {"timestamp": timestamp}
            if thinking_content:
                additional_kwargs["thinking_content"] = thinking_content
            return AIMessage(
                content=content,
                additional_kwargs=additional_kwargs,
            )
        if role == "system":
            return SystemMessage(content=content)
        return None

    def recent_tool_names(self, window: int = 10) -> list[str]:
        """Return tool names from the last *window* raw conversation
        entries, for use in recent-lookup detection.

        Reads ``_conversation.value`` directly (not the filtered
        ``.messages`` property) so that ``metadata_type: tool_calls``
        entries are included.
        """
        if self.ephemeral:
            return []
        if not self._conversation:
            return []
        raw = self._conversation.value
        if not isinstance(raw, list):
            return []
        names: list[str] = []
        for entry in raw[-window:]:
            if not isinstance(entry, dict):
                continue
            if entry.get("metadata_type") != "tool_calls":
                continue
            for tc in entry.get("tool_calls", []):
                name = tc.get("name", "")
                if name:
                    names.append(name)
        return names

    @staticmethod
    def _is_internal_context(message: BaseMessage) -> bool:
        """Return True when *message* is an internal context injection
        that should be skipped (e.g. knowledge recall scaffolding)."""
        return bool(
            hasattr(message, "additional_kwargs")
            and message.additional_kwargs
            and message.additional_kwargs.get("internal_context"),
        )
