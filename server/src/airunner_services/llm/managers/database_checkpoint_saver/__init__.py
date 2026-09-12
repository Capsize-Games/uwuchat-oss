"""Custom LangGraph checkpointer that persists to the Conversation database.

Decomposed into focused modules:

- ``_helpers`` — pure helpers (config/checkpoint builders, LRU cache
  store, DB-visible message counting)
- ``_base`` — shared instance state (__init__) and message-trimming logic
- ``_write`` — checkpoint writes (put, put_writes, clear_checkpoints,
  clear_thread)
- ``_read`` — checkpoint reads (get_tuple, get, list)

``DatabaseCheckpointSaver`` composes the base with the read/write mixins
so every abstract method of LangGraph's ``BaseCheckpointSaver`` is
implemented.  ``DatabaseChatMessageHistory`` is re-exported here and is
resolved through this package module at call time, so runtime patches of
``database_checkpoint_saver.DatabaseChatMessageHistory`` keep working.
"""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver

from airunner_services.llm.managers.database_chat_message_history import (
    DatabaseChatMessageHistory,
)

from ._base import DatabaseCheckpointSaverBase
from ._helpers import _CHECKPOINT_STATE_MAX_SIZE
from ._read import ReadMixin
from ._write import WriteMixin


class DatabaseCheckpointSaver(
    DatabaseCheckpointSaverBase, WriteMixin, ReadMixin, BaseCheckpointSaver
):
    """LangGraph checkpoint saver that persists conversation state to the
    database.

    This integrates LangGraph's checkpointing system with AI Runner's
    Conversation model, ensuring conversation state is properly saved and
    can be restored.
    """
