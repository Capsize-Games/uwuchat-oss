"""LangChain message history that persists to the Conversation database.

The former monolithic ``database_chat_message_history.py`` module was
split into this package; the composed ``DatabaseChatMessageHistory``
class below keeps the import path and behavior unchanged.
"""

from langchain_core.chat_history import BaseChatMessageHistory

from airunner_services.llm.managers.database_chat_message_history._base import (
    DatabaseChatMessageHistoryBase,
)
from airunner_services.llm.managers.database_chat_message_history._format import (
    _FALLBACK_LABEL,
    _STATUS_TEMPLATES,
    _TOOL_LABEL_MAP,
    _friendly_tool_status,
    activities_phrase,
)
from airunner_services.llm.managers.database_chat_message_history._message_build import (
    DatabaseChatMessageBuildMixin,
)
from airunner_services.llm.managers.database_chat_message_history._messages import (
    DatabaseChatMessageCRUDMixin,
)
from airunner_services.llm.managers.database_chat_message_history._session import (
    DatabaseChatMessageSessionMixin,
)
from airunner_services.llm.managers.database_chat_message_history._tool_messages import (
    DatabaseChatToolMessageMixin,
)


class DatabaseChatMessageHistory(
    DatabaseChatMessageCRUDMixin,
    DatabaseChatToolMessageMixin,
    DatabaseChatMessageBuildMixin,
    DatabaseChatMessageSessionMixin,
    DatabaseChatMessageHistoryBase,
    BaseChatMessageHistory,
):
    """Chat message history that stores messages in the Conversation
    database.

    This class integrates LangChain's memory system with AI Runner's
    Conversation model, ensuring that all chat messages are properly
    persisted to the database and can be loaded later.

    Ephemeral Mode:
        When ephemeral=True, messages are kept in memory only and never
        saved to the database. This is useful for:
        - API requests that shouldn't pollute conversation history
        - Batch processing tasks (e.g., book classification)
        - Temporary analysis or classification tasks
        - Any operation that should leave no trace in conversation
          history
    """


# The formatting helpers are re-exported for backward compatibility:
# existing tests import them from the package root.
__all__ = [
    "_FALLBACK_LABEL",
    "_STATUS_TEMPLATES",
    "_TOOL_LABEL_MAP",
    "DatabaseChatMessageHistory",
    "_friendly_tool_status",
    "activities_phrase",
]
