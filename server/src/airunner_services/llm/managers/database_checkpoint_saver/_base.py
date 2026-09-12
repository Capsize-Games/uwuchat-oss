"""Shared base state and trimming logic for the checkpoint saver."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, List, Optional

from langchain_core.messages import BaseMessage
from langchain_core.messages.utils import count_tokens_approximately

import airunner_services.llm.managers.database_checkpoint_saver as _pkg
from airunner_services.settings import AIRUNNER_LOG_LEVEL
from airunner_services.utils.application import get_logger


class DatabaseCheckpointSaverBase:
    """Shared instance state and message-trimming helpers.

    The concrete ``DatabaseCheckpointSaver`` composes this with the read
    and write mixins, satisfying every abstract method of LangGraph's
    ``BaseCheckpointSaver``.
    """

    def __init__(
        self,
        conversation_id: Optional[int] = None,
        stateless: bool = False,
        ephemeral: bool = False,
        max_history_tokens: Optional[int] = None,
    ):
        """Initialize the database checkpoint saver.

        Args:
            conversation_id: Optional conversation ID to use.
            stateless: If True, disable checkpoint persistence.
            ephemeral: If True, disable conversation history persistence.
            max_history_tokens: When set, trim history to this token
                budget before returning a checkpoint.
        """
        super().__init__()
        self.logger = get_logger(__package__, AIRUNNER_LOG_LEVEL)
        self.conversation_id = conversation_id
        self.ephemeral = ephemeral
        self.message_history = _pkg.DatabaseChatMessageHistory(
            conversation_id, ephemeral=(ephemeral or stateless)
        )
        self.stateless = stateless
        self.max_history_tokens = max_history_tokens
        # Instance-level LRU cache — keyed by thread_id (str(conversation_id)).
        # OrderedDict gives O(1) move-to-end for LRU ordering.
        self._checkpoint_state: OrderedDict[str, Any] = OrderedDict()
        # Track how many messages get_tuple() returned as the turn base
        # so put() can compute the incremental delta without comparing
        # trimmed-state counts against full-DB counts.
        self._turn_base_count: int = 0

    @staticmethod
    def _tool_call_group_size(
        messages: List[BaseMessage], start_idx: int,
    ) -> int:
        """Return the size of one atomic tool-call group at *start_idx*.

        When ``messages[start_idx]`` is an ``AIMessage`` with ``tool_calls``,
        the group includes it plus every immediately-following ``ToolMessage``
        whose ``tool_call_id`` matches one of the tool calls.  Returns 1 for
        any message that is not part of a tool-call group.

        This keeps trimming from splitting a ``ToolMessage`` from its parent
        ``AIMessage``, which would cause the amnesia bug or an API rejection.
        """
        first = messages[start_idx]
        if first.__class__.__name__ != "AIMessage":
            return 1
        tool_calls = getattr(first, "tool_calls", None)
        if not tool_calls:
            return 1
        tool_ids = {tc["id"] for tc in tool_calls if tc.get("id")}
        if not tool_ids:
            return 1
        count = 1
        for i in range(start_idx + 1, len(messages)):
            msg = messages[i]
            if msg.__class__.__name__ != "ToolMessage":
                break
            tc_id = getattr(msg, "tool_call_id", None)
            if tc_id in tool_ids:
                count += 1
                tool_ids.discard(tc_id)
            else:
                break
        return count

    def _trim_messages(self, messages: List[BaseMessage]) -> List[BaseMessage]:
        """Trim message history to fit within max_history_tokens budget.

        Removes oldest messages (excluding the last user/assistant pair) when
        the token count exceeds the configured limit, and truncates oversized
        ToolMessage content so a single large search/newspaper result does not
        consume budget on every subsequent turn.  Returns the original list
        unchanged when no limit is set or it is not exceeded.

        Tool-call groups (``AIMessage`` with ``tool_calls`` + all of its
        ``ToolMessage`` children) are dropped atomically — never split.
        """
        if not self.max_history_tokens or not messages:
            return messages

        total_tokens = count_tokens_approximately(messages)
        if total_tokens <= self.max_history_tokens:
            return messages

        trimmed = list(messages)
        while len(trimmed) > 2:
            group_size = self._tool_call_group_size(trimmed, 0)
            # Never drop a group that would leave fewer than 2 messages.
            if len(trimmed) - group_size < 2:
                break
            if count_tokens_approximately(trimmed) <= self.max_history_tokens:
                break
            for _ in range(group_size):
                trimmed.pop(0)

        # Truncate oversized ToolMessage content so a single large
        # search/newspaper result does not consume budget on every
        # subsequent turn.  The current turn's generation already used
        # the full result — future turns only need a summary.
        from airunner_services.llm.managers.message_utils import (
            truncate_oversized_tool_messages,
        )
        truncate_oversized_tool_messages(trimmed)

        self.logger.info(
            "History trimmed from %d to %d messages to fit %d token budget (%d tokens)",
            len(messages),
            len(trimmed),
            self.max_history_tokens,
            count_tokens_approximately(trimmed),
        )
        return trimmed
