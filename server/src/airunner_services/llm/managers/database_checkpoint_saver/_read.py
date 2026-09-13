"""Checkpoint read operations for the database checkpoint saver."""

from __future__ import annotations

from typing import Any, Dict, Iterator, Optional

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import Checkpoint, CheckpointTuple

from ._helpers import (
    _build_checkpoint,
    _build_metadata,
    _copy_with_trimmed,
    _db_visible_message_count,
    _diag_message_summary,
)


class ReadMixin:
    """Checkpoint reads: get_tuple(), get(), and list()."""

    def get_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        """Fetch a checkpoint tuple using the given configuration.

        Args:
            config: Configuration specifying which checkpoint to retrieve.

        Returns:
            The requested checkpoint tuple, or None if not found.
        """
        try:
            if self.stateless:
                self.logger.debug(
                    "Stateless mode: returning None (no checkpoint "
                    "restoration)"
                )
                self._turn_base_count = 0
                return None
            thread_id = config.get("configurable", {}).get("thread_id")
            cached = self._cached_tuple(config, thread_id)
            if cached is not None:
                return cached
            return self._db_tuple(config)
        except Exception as e:
            self.logger.error(
                "Error retrieving checkpoint: %s", e, exc_info=True
            )
            self._turn_base_count = 0
            return None

    def _cached_tuple(self, config: RunnableConfig, thread_id: Optional[str]):
        """Return the in-memory checkpoint tuple for *thread_id*.

        Returns None when the cache entry is missing or stale, so the
        caller falls through to the database.
        """
        if not thread_id or thread_id not in self._checkpoint_state:
            return None
        state = self._checkpoint_state[thread_id]
        if self._cache_is_stale(thread_id, state):
            return None
        self.logger.info(
            "[DIAG get_tuple in-mem] thread=%s msgs=%s",
            thread_id,
            _diag_message_summary(state["messages"]),
        )
        trimmed = self._trim_messages(state["messages"])
        checkpoint_data = _copy_with_trimmed(
            state["checkpoint"], state["messages"], trimmed
        )
        self._turn_base_count = len(trimmed)
        return CheckpointTuple(
            config=config,
            checkpoint=checkpoint_data,
            metadata=state["metadata"],
            parent_config=None,
        )

    def _cache_is_stale(self, thread_id: str, state: dict) -> bool:
        """Return True (and drop the cache entry) when the DB now has
        more visible messages than the cached checkpoint.

        Proactive/interjection messages are appended to
        Conversation.value by a background thread that bypasses the
        checkpointer; a growing DB count means the cache is out of date.
        """
        self.message_history._load_conversation()
        raw_conv = self.message_history._conversation
        db_value = raw_conv.value if raw_conv and raw_conv.value else []
        db_visible = _db_visible_message_count(db_value)
        if db_visible <= len(state["messages"]):
            return False
        self.logger.info(
            "Cache stale (db=%d cached=%d) — reloading from DB",
            db_visible,
            len(state["messages"]),
        )
        del self._checkpoint_state[thread_id]
        return True

    def _db_tuple(self, config: RunnableConfig):
        """Build a checkpoint tuple from the persisted DB messages."""
        messages = self.message_history.messages
        if not messages:
            self._turn_base_count = 0
            return None
        messages = self._trim_messages(messages)
        self._turn_base_count = len(messages)
        return CheckpointTuple(
            config=config,
            checkpoint=_build_checkpoint(messages),
            metadata=_build_metadata(messages),
            parent_config=None,
        )

    def get(self, config: RunnableConfig) -> Optional[Checkpoint]:
        """Retrieve a checkpoint payload from the database.

        Args:
            config: Runtime configuration.

        Returns:
            Checkpoint data or None if not found.
        """
        checkpoint_tuple = self.get_tuple(config)
        if checkpoint_tuple is None:
            return None
        return checkpoint_tuple.checkpoint

    def list(
        self,
        config: Optional[RunnableConfig],
        *,
        filter: Optional[Dict[str, Any]] = None,
        before: Optional[RunnableConfig] = None,
        limit: Optional[int] = None,
    ) -> Iterator[CheckpointTuple]:
        """List checkpoints from the database.

        Args:
            config: Runtime configuration.
            filter: Optional filter criteria.
            before: Optional config to list checkpoints before.
            limit: Optional limit on number of checkpoints.

        Yields:
            Checkpoint tuples.
        """
        del before
        if config is None:
            return
        current = self.get_tuple(config)
        if current:
            yield current
