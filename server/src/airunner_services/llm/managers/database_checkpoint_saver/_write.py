"""Checkpoint write operations for the database checkpoint saver."""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional, Sequence, Tuple

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import Checkpoint, CheckpointMetadata

from ._helpers import (
    _checkpoint_id_from,
    _fresh_config,
    _store_checkpoint_state,
)


class WriteMixin:
    """Checkpoint persistence: put(), put_writes(), and clearing."""

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: Optional[Dict[str, Any]] = None,
    ) -> RunnableConfig:
        """Save a checkpoint to the database.

        Args:
            config: Runtime configuration.
            checkpoint: Checkpoint data to save.
            metadata: Checkpoint metadata.
            new_versions: Optional version information.

        Returns:
            Updated configuration with checkpoint ID.
        """
        del new_versions
        try:
            if self.stateless:
                return _fresh_config()
            self.logger.debug(
                "DatabaseCheckpointSaver.put() called for conversation %s",
                self.conversation_id,
            )
            messages = self._put_messages(checkpoint)
            if messages is not None:
                early = self._persist_messages(messages, checkpoint, metadata)
                if early is not None:
                    return early
            checkpoint_id = _checkpoint_id_from(checkpoint)
            return {
                "configurable": {
                    "thread_id": str(self.message_history.conversation_id),
                    "checkpoint_id": checkpoint_id,
                }
            }
        except Exception as e:
            self.logger.error("Error saving checkpoint: %s", e, exc_info=True)
            return config

    def _put_messages(self, checkpoint: Checkpoint):
        """Return the checkpoint's channel messages, or None if absent."""
        if "messages" not in checkpoint.get("channel_values", {}):
            return None
        messages = checkpoint["channel_values"]["messages"]
        self.logger.debug("Checkpoint has %d messages", len(messages))
        if messages:
            last_msg = messages[-1]
            self.logger.debug(
                "Checkpoint persistence preview - type=%s, content=%r",
                type(last_msg).__name__,
                getattr(last_msg, "content", "")[:100],
            )
        return messages

    def _persist_messages(
        self, messages: list, checkpoint: Checkpoint, metadata: Any
    ):
        """Append the message delta and cache the checkpoint.

        Returns a config dict for early return when no conversation is
        available, else None so the caller produces the normal config.
        """
        self.message_history._load_conversation()
        if not self.message_history.conversation_id:
            self.logger.warning(
                "No conversation_id available; skipping DB "
                "message persistence for this checkpoint"
            )
            return {
                "configurable": {
                    "thread_id": str(uuid.uuid4()),
                    "checkpoint_id": _checkpoint_id_from(checkpoint),
                }
            }
        self._append_delta(messages)
        self._cache_checkpoint(messages, checkpoint, metadata)
        return None

    def _append_delta(self, messages: list) -> None:
        """Persist only the messages beyond the tracked turn base."""
        base_count = self._turn_base_count
        checkpoint_count = len(messages)
        self.logger.debug(
            "Persistence delta: base=%d checkpoint=%d",
            base_count,
            checkpoint_count,
        )
        if checkpoint_count > base_count:
            new_messages = messages[base_count:]
            self.logger.debug(
                "Adding %d new messages to conversation",
                len(new_messages),
            )
            for msg in new_messages:
                self.message_history.add_message(msg)
            self._turn_base_count = checkpoint_count
            self.logger.debug(
                "Appended %d new messages to conversation %s",
                len(new_messages),
                self.message_history.conversation_id,
            )
        elif checkpoint_count == base_count:
            self.logger.debug("No new messages to save (matches turn base)")
        else:
            self.logger.warning(
                "Checkpoint shrank below tracked turn base "
                "(base=%d, checkpoint=%d) — this should not "
                "happen and indicates a state-tracking bug",
                base_count,
                checkpoint_count,
            )

    def _cache_checkpoint(
        self, messages: list, checkpoint: Checkpoint, metadata: Any
    ) -> None:
        """Store the checkpoint in the LRU cache when messages exist."""
        if not messages:
            self.logger.warning(
                "Skipping checkpoint save - no changes detected "
                "(%d messages)",
                len(messages),
            )
            return
        thread_id = str(self.message_history.conversation_id)
        _store_checkpoint_state(
            self._checkpoint_state,
            thread_id,
            checkpoint,
            metadata,
            messages,
            self.logger,
        )

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[Tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """Store intermediate writes from graph execution.

        Args:
            config: Runtime configuration.
            writes: Sequence of (channel, value) writes to store.
            task_id: Unique identifier for the task.
            task_path: Task path in the graph.
        """
        del task_path
        # NOTE: intermediate writes are stashed in memory only
        # (self._checkpoint_state).  A server restart between a tool call
        # and the final LLM response will cause tool side-effects (write_file,
        # record_knowledge, generate_image, etc.) to be re-executed.
        # To persist writes across restarts: add a DB table for pending writes
        # keyed by (thread_id, task_id); upsert on put(); filter already-
        # persisted writes in get_tuple().
        thread_id = (
            config.get("configurable", {}).get("thread_id") if config else None
        )
        if thread_id and writes:
            state = self._checkpoint_state.get(thread_id)
            if state is not None:
                pending = state.setdefault("pending_writes", {})
                pending[task_id] = list(writes)
                self.logger.debug(
                    "put_writes: stored %d writes for task %s thread %s",
                    len(writes),
                    task_id,
                    thread_id,
                )
            else:
                self.logger.warning(
                    "put_writes: no checkpoint state for thread %s — "
                    "intermediate writes not persisted; tool results may "
                    "re-execute on restart",
                    thread_id,
                )

    def clear_checkpoints(self, clear_history: bool = True) -> None:
        """Clear checkpoint cache and optionally wipe stored history.

        Args:
            clear_history: When True (default), also clear the persisted
                conversation transcript. Set to False when you only need
                to drop LangGraph's cached checkpoints but want to keep
                the existing database history intact.
        """
        # CRITICAL FIX: Only clear checkpoint state for THIS
        # conversation's thread, not ALL conversations.  Previously this
        # looped over every thread in the cache, wiping unrelated
        # conversations.
        thread_id = str(self.conversation_id) if self.conversation_id else None
        if thread_id and thread_id in self._checkpoint_state:
            del self._checkpoint_state[thread_id]
            self.logger.info(
                "Cleared checkpoint state for thread %s", thread_id
            )
        else:
            self.logger.debug(
                "No checkpoint state to clear for thread %s", thread_id
            )
        if clear_history:
            self.message_history.clear()
            self.logger.info(
                "Cleared message history for conversation %s",
                self.conversation_id,
            )

    def clear_thread(self, thread_id: str) -> None:
        """Clear checkpoint state for a specific thread.

        Args:
            thread_id: The thread ID to clear.
        """
        if thread_id in self._checkpoint_state:
            del self._checkpoint_state[thread_id]
            self.logger.info(
                "Cleared checkpoint state for thread %s", thread_id
            )
