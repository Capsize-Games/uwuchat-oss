"""Unit tests for DatabaseCheckpointSaver."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from langchain_core.messages import HumanMessage, AIMessage


def _make_saver(
    conversation_id: int = 1, stateless: bool = False, ephemeral: bool = True
):
    """Return a DatabaseCheckpointSaver with DB I/O fully mocked out."""
    with patch(
        "airunner_services.llm.managers.database_checkpoint_saver.DatabaseChatMessageHistory"
    ) as MockHistory:
        mock_history = MagicMock()
        mock_history.conversation_id = conversation_id
        mock_history.messages = []
        mock_history._conversation = None
        MockHistory.return_value = mock_history

        from airunner_services.llm.managers.database_checkpoint_saver import (
            DatabaseCheckpointSaver,
        )

        saver = DatabaseCheckpointSaver(
            conversation_id=conversation_id,
            stateless=stateless,
            ephemeral=ephemeral,
        )
        saver.message_history = mock_history
        return saver, mock_history


def _make_checkpoint(messages: list, checkpoint_id: str | None = None) -> dict:
    """Build a minimal checkpoint dict."""
    return {
        "v": 1,
        "id": checkpoint_id or str(uuid.uuid4()),
        "ts": "",
        "channel_values": {"messages": messages},
        "channel_versions": {},
        "versions_seen": {},
        "updated_channels": None,
    }


def _make_config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


# ---------------------------------------------------------------------------
# Test 1: put() only appends NEW messages
# ---------------------------------------------------------------------------


class TestPutAppendsOnlyNewMessages:
    def test_appends_messages_beyond_existing_db_count(self):
        saver, mock_history = _make_saver(conversation_id=42)
        thread_id = "42"
        msgs = [HumanMessage(content="hi"), AIMessage(content="hello")]
        checkpoint = _make_checkpoint(msgs)
        metadata = {"source": "update", "step": 2, "parents": {}}

        # Simulate turn base already has 1 message (from get_tuple)
        saver._turn_base_count = 1
        mock_history._load_conversation = MagicMock()
        mock_history._conversation = MagicMock()
        mock_history._conversation.value = []

        saver.put(_make_config(thread_id), checkpoint, metadata)

        # Only the second message (AIMessage, beyond base=1) persisted
        assert mock_history.add_message.call_count == 1
        added = mock_history.add_message.call_args[0][0]
        assert isinstance(added, AIMessage)

    def test_no_messages_added_when_counts_match(self):
        saver, mock_history = _make_saver(conversation_id=5)
        thread_id = "5"
        msgs = [HumanMessage(content="x")]
        checkpoint = _make_checkpoint(msgs)
        metadata = {"source": "update", "step": 1, "parents": {}}

        # Turn base matches checkpoint size
        saver._turn_base_count = 1
        mock_history._load_conversation = MagicMock()
        mock_history._conversation = MagicMock()
        mock_history._conversation.value = []

        saver.put(_make_config(thread_id), checkpoint, metadata)

        mock_history.add_message.assert_not_called()

    def test_checkpoint_stored_in_memory_after_put(self):
        saver, mock_history = _make_saver(conversation_id=7)
        thread_id = "7"
        msgs = [HumanMessage(content="store me")]
        checkpoint = _make_checkpoint(msgs)
        metadata = {"source": "update", "step": 1, "parents": {}}

        mock_history._load_conversation = MagicMock()
        mock_history._conversation = MagicMock()
        mock_history._conversation.value = []

        saver.put(_make_config(thread_id), checkpoint, metadata)

        assert thread_id in saver._checkpoint_state
        assert saver._checkpoint_state[thread_id]["messages"] == msgs


# ---------------------------------------------------------------------------
# Test 2: get_tuple() returns None in stateless mode
# ---------------------------------------------------------------------------


class TestGetTupleStateless:
    def test_returns_none_when_stateless(self):
        saver, _mock_history = _make_saver(conversation_id=1, stateless=True)
        result = saver.get_tuple(_make_config("1"))
        assert result is None


# ---------------------------------------------------------------------------
# Test 3: get_tuple() returns in-memory state without hitting DB
# ---------------------------------------------------------------------------


class TestGetTupleFromMemory:
    def test_returns_in_memory_state(self):
        saver, mock_history = _make_saver(conversation_id=10)
        thread_id = "10"
        msgs = [HumanMessage(content="cached")]
        checkpoint = _make_checkpoint(msgs)
        metadata = {"source": "update", "step": 1, "parents": {}}

        # Pre-populate the in-memory cache
        saver._checkpoint_state[thread_id] = {
            "checkpoint": checkpoint,
            "metadata": metadata,
            "messages": msgs,
        }

        result = saver.get_tuple(_make_config(thread_id))

        assert result is not None
        assert result.checkpoint["channel_values"]["messages"] == msgs
        # DB messages property should NOT have been accessed
        (
            mock_history.messages.assert_not_called()
            if hasattr(mock_history.messages, "assert_not_called")
            else None
        )


# ---------------------------------------------------------------------------
# Test 4: get_tuple() falls back to DB when in-memory state is absent
# ---------------------------------------------------------------------------


class TestGetTupleFallsBackToDb:
    def test_falls_back_to_db_messages(self):
        saver, mock_history = _make_saver(conversation_id=20)
        thread_id = "99"  # not in in-memory cache
        db_messages = [
            HumanMessage(content="from db"),
            AIMessage(content="reply"),
        ]
        mock_history.messages = db_messages

        result = saver.get_tuple(_make_config(thread_id))

        assert result is not None
        assert result.checkpoint["channel_values"]["messages"] == db_messages

    def test_returns_none_when_db_empty(self):
        saver, mock_history = _make_saver(conversation_id=21)
        mock_history.messages = []

        result = saver.get_tuple(_make_config("999"))

        assert result is None


# ---------------------------------------------------------------------------
# Test 5: clear_checkpoints() removes the thread from _checkpoint_state
# ---------------------------------------------------------------------------


class TestClearCheckpoints:
    def test_clears_this_conversations_thread(self):
        saver, mock_history = _make_saver(conversation_id=30)
        thread_id = "30"
        saver._checkpoint_state[thread_id] = {
            "messages": [],
            "checkpoint": {},
            "metadata": {},
        }

        saver.clear_checkpoints(clear_history=False)

        assert thread_id not in saver._checkpoint_state

    def test_does_not_clear_other_threads(self):
        saver, mock_history = _make_saver(conversation_id=31)
        saver._checkpoint_state["31"] = {
            "messages": [],
            "checkpoint": {},
            "metadata": {},
        }
        saver._checkpoint_state["999"] = {
            "messages": [],
            "checkpoint": {},
            "metadata": {},
        }

        saver.clear_checkpoints(clear_history=False)

        assert "999" in saver._checkpoint_state

    def test_clears_message_history_when_requested(self):
        saver, mock_history = _make_saver(conversation_id=32)
        saver.clear_checkpoints(clear_history=True)
        mock_history.clear.assert_called_once()

    def test_does_not_clear_message_history_when_not_requested(self):
        saver, mock_history = _make_saver(conversation_id=33)
        saver.clear_checkpoints(clear_history=False)
        mock_history.clear.assert_not_called()


# ---------------------------------------------------------------------------
# Test 6: Two instances with different conversation_ids do not share state
# ---------------------------------------------------------------------------


class TestInstanceIsolation:
    def test_different_instances_have_separate_checkpoint_state(self):
        saver_a, mock_a = _make_saver(conversation_id=100)
        saver_b, mock_b = _make_saver(conversation_id=200)

        saver_a._checkpoint_state["100"] = {
            "messages": ["a"],
            "checkpoint": {},
            "metadata": {},
        }

        # saver_b must not see saver_a's state
        assert "100" not in saver_b._checkpoint_state

    def test_put_into_one_instance_does_not_contaminate_another(self):
        saver_a, mock_a = _make_saver(conversation_id=101)
        saver_b, mock_b = _make_saver(conversation_id=102)

        msgs = [HumanMessage(content="isolation test")]
        checkpoint = _make_checkpoint(msgs)
        metadata = {"source": "update", "step": 1, "parents": {}}

        mock_a._load_conversation = MagicMock()
        mock_a._conversation = MagicMock()
        mock_a._conversation.value = []

        saver_a.put(_make_config("101"), checkpoint, metadata)

        # saver_b's state should be untouched
        assert "101" not in saver_b._checkpoint_state
        assert len(saver_b._checkpoint_state) == 0

    def test_lru_eviction_caps_at_max_size(self):
        from airunner_services.llm.managers.database_checkpoint_saver import (
            _CHECKPOINT_STATE_MAX_SIZE,
        )

        saver, _ = _make_saver(conversation_id=999)
        # Fill beyond max
        for i in range(_CHECKPOINT_STATE_MAX_SIZE + 5):
            saver._checkpoint_state[str(i)] = {
                "messages": [],
                "checkpoint": {},
                "metadata": {},
            }
            saver._checkpoint_state.move_to_end(str(i))
            if len(saver._checkpoint_state) > _CHECKPOINT_STATE_MAX_SIZE:
                saver._checkpoint_state.popitem(last=False)

        assert len(saver._checkpoint_state) <= _CHECKPOINT_STATE_MAX_SIZE


# ---------------------------------------------------------------------------
# Test 7: stateless=True alone (with ephemeral=False) still produces
#         an ephemeral DatabaseChatMessageHistory
# ---------------------------------------------------------------------------


class TestStatelessImpliesEphemeral:
    """stateless=True is documented as "disable checkpoint persistence" —
    it should also prevent the eager DatabaseChatMessageHistory DB load,
    just as ephemeral=True does, without requiring callers to pass both
    flags in sync."""

    def test_message_history_ephemeral_when_stateless_but_not_ephemeral(
        self,
    ):
        with patch(
            "airunner_services.llm.managers.database_checkpoint_saver."
            "DatabaseChatMessageHistory"
        ) as MockHistory:
            mock_history = MagicMock()
            mock_history.conversation_id = 1
            mock_history.messages = []
            mock_history._conversation = None
            MockHistory.return_value = mock_history

            from airunner_services.llm.managers.database_checkpoint_saver import (
                DatabaseCheckpointSaver,
            )

            _ = DatabaseCheckpointSaver(
                conversation_id=1,
                stateless=True,
                ephemeral=False,
            )

            # The constructed DatabaseChatMessageHistory must have
            # ephemeral=True because stateless=True was passed.
            call_kwargs = MockHistory.call_args[1]
            assert call_kwargs.get("ephemeral") is True, (
                "DatabaseChatMessageHistory must receive ephemeral=True "
                "when stateless=True, even if ephemeral=False explicitly"
            )


# ---------------------------------------------------------------------------
# Test: _tool_call_group_size returns correct atomic group sizes
# ---------------------------------------------------------------------------


def _make_ai_with_tool_calls(tool_call_ids: list[str]) -> AIMessage:
    """Build an AIMessage carrying the given tool call IDs."""
    return AIMessage(
        content="",
        tool_calls=[
            {"id": tid, "name": f"tool_{tid}", "args": {}}
            for tid in tool_call_ids
        ],
    )


def _make_tool_msg(tool_call_id: str, content: str = "result") -> MagicMock:
    """Build a ToolMessage-like mock with the given tool_call_id."""
    from langchain_core.messages import ToolMessage
    return ToolMessage(content=content, tool_call_id=tool_call_id)


class TestToolCallGroupSize:
    """Verify _tool_call_group_size correctly identifies atomic groups."""

    def test_plain_aimessage_returns_1(self):
        from airunner_services.llm.managers.database_checkpoint_saver import (
            DatabaseCheckpointSaver,
        )
        msgs = [AIMessage(content="hello")]
        assert DatabaseCheckpointSaver._tool_call_group_size(msgs, 0) == 1

    def test_human_message_returns_1(self):
        from airunner_services.llm.managers.database_checkpoint_saver import (
            DatabaseCheckpointSaver,
        )
        msgs = [HumanMessage(content="hi")]
        assert DatabaseCheckpointSaver._tool_call_group_size(msgs, 0) == 1

    def test_single_tool_call_with_result(self):
        from airunner_services.llm.managers.database_checkpoint_saver import (
            DatabaseCheckpointSaver,
        )
        msgs = [
            _make_ai_with_tool_calls(["id1"]),
            _make_tool_msg("id1"),
            AIMessage(content="final"),
        ]
        # AIMessage + ToolMessage
        assert DatabaseCheckpointSaver._tool_call_group_size(msgs, 0) == 2

    def test_multiple_tool_calls_with_results(self):
        from airunner_services.llm.managers.database_checkpoint_saver import (
            DatabaseCheckpointSaver,
        )
        msgs = [
            _make_ai_with_tool_calls(["id1", "id2"]),
            _make_tool_msg("id1"),
            _make_tool_msg("id2"),
            AIMessage(content="final"),
        ]
        # AIMessage + 2 ToolMessages
        assert DatabaseCheckpointSaver._tool_call_group_size(msgs, 0) == 3

    def test_tool_message_without_tool_calls_is_not_a_group(self):
        from airunner_services.llm.managers.database_checkpoint_saver import (
            DatabaseCheckpointSaver,
        )
        msgs = [_make_tool_msg("orphan")]
        assert DatabaseCheckpointSaver._tool_call_group_size(msgs, 0) == 1

    def test_non_matching_tool_message_breaks_group(self):
        from airunner_services.llm.managers.database_checkpoint_saver import (
            DatabaseCheckpointSaver,
        )
        msgs = [
            _make_ai_with_tool_calls(["id1"]),
            _make_tool_msg("id2"),  # doesn't match → breaks group
            AIMessage(content="final"),
        ]
        assert DatabaseCheckpointSaver._tool_call_group_size(msgs, 0) == 1


class TestTrimMessagesPreservesToolGroups:
    """Verify _trim_messages never splits a ToolMessage from its parent."""

    def test_drops_entire_tool_group_atomically(self):
        saver, mock_history = _make_saver(conversation_id=1)
        saver.max_history_tokens = 10  # force trimming

        msgs = [
            _make_ai_with_tool_calls(["id1"]),
            _make_tool_msg("id1", "a" * 200),  # large content → high tokens
            AIMessage(content="first reply"),
            HumanMessage(content="second question"),
            AIMessage(content="second reply"),
        ]

        result = saver._trim_messages(msgs)

        # The tool-call group must be either fully present or fully absent.
        tool_ids_present = {
            getattr(m, "tool_call_id", "")
            for m in result
            if m.__class__.__name__ == "ToolMessage"
        }
        ai_with_tool_calls = [
            m for m in result
            if m.__class__.__name__ == "AIMessage"
            and getattr(m, "tool_calls", None)
        ]
        ai_tool_ids = set()
        for ai in ai_with_tool_calls:
            for tc in getattr(ai, "tool_calls", []):
                ai_tool_ids.add(tc.get("id", ""))

        # Every ToolMessage's tool_call_id must have a matching AIMessage
        for tid in tool_ids_present:
            assert tid in ai_tool_ids, (
                f"ToolMessage {tid} has no parent AIMessage with tool_calls"
            )

        # At least 2 messages must survive
        assert len(result) >= 2

    def test_does_not_split_group_when_budget_tight(self):
        saver, mock_history = _make_saver(conversation_id=1)
        # Very tight budget — should keep the last 2, dropping everything
        # else atomically.
        saver.max_history_tokens = 1

        msgs = [
            _make_ai_with_tool_calls(["id1"]),
            _make_tool_msg("id1", "x" * 500),
            AIMessage(content="old reply"),
            HumanMessage(content="recent question"),
            AIMessage(content="recent reply"),
        ]

        result = saver._trim_messages(msgs)

        # The tool-call group (first 2) should be dropped together.
        # The final 2 (recent exchange) must survive.
        assert len(result) >= 2
        # No orphan ToolMessages
        tool_msgs = [m for m in result
                     if m.__class__.__name__ == "ToolMessage"]
        if tool_msgs:
            ai_with_tools = [
                m for m in result
                if m.__class__.__name__ == "AIMessage"
                and getattr(m, "tool_calls", None)
            ]
            ai_ids = {
                tid
                for ai in ai_with_tools
                for tc in getattr(ai, "tool_calls", [])
                if tc.get("id")
                for tid in [tc["id"]]
            }
            for tm in tool_msgs:
                assert getattr(tm, "tool_call_id", "") in ai_ids


# ---------------------------------------------------------------------------
# _turn_base_count tracking — regression tests for the persistence-
# freeze bug where trimming caused checkpoint_count < existing DB count.
# ---------------------------------------------------------------------------


class TestTurnBaseCountPersistence:
    """put() uses _turn_base_count (not DB count) to compute deltas."""

    def test_persists_delta_after_trimming(self):
        """Regression: trimming shrinks checkpoint but base tracks it."""
        saver, mock_history = _make_saver(conversation_id=200)
        mock_history._load_conversation = MagicMock()
        mock_history._conversation = MagicMock()
        mock_history._conversation.value = []

        # Simulate get_tuple() returning a trimmed base of 2 messages.
        saver._turn_base_count = 2

        # put() receives checkpoint with 5 messages (trimming added 3)
        msgs = [
            HumanMessage(content="old"),
            AIMessage(content="old reply"),
            HumanMessage(content="new1"),
            AIMessage(content="new1 reply"),
            AIMessage(content="new2 reply"),
        ]
        checkpoint = _make_checkpoint(msgs)
        metadata = {"source": "update", "step": 5, "parents": {}}

        saver.put(_make_config("200"), checkpoint, metadata)

        # Only messages[2:] (3 new) should be persisted
        assert mock_history.add_message.call_count == 3
        # _turn_base_count updated to new checkpoint size
        assert saver._turn_base_count == 5

    def test_two_sequential_puts_persist_incremental_deltas(self):
        """Sequential put() calls only persist their own delta."""
        saver, mock_history = _make_saver(conversation_id=201)
        mock_history._load_conversation = MagicMock()
        mock_history._conversation = MagicMock()
        mock_history._conversation.value = []

        # get_tuple() returned base of 3
        saver._turn_base_count = 3

        # First put: 2 new messages
        msgs1 = [
            HumanMessage(content="a"),
            AIMessage(content="b"),
            HumanMessage(content="c"),
            AIMessage(content="d"),
            HumanMessage(content="e"),
        ]
        saver.put(
            _make_config("201"),
            _make_checkpoint(msgs1),
            {"source": "update", "step": 5, "parents": {}},
        )
        assert mock_history.add_message.call_count == 2
        assert saver._turn_base_count == 5

        # Second put in same turn: 1 more message
        msgs2 = msgs1 + [AIMessage(content="f")]
        saver.put(
            _make_config("201"),
            _make_checkpoint(msgs2),
            {"source": "update", "step": 6, "parents": {}},
        )
        # Only 1 additional message (not the previous 2 again)
        assert mock_history.add_message.call_count == 3

    def test_else_branch_logs_warning_and_does_not_raise(self):
        """checkpoint_count < base_count logs a warning, no exception."""
        saver, mock_history = _make_saver(conversation_id=202)
        mock_history._load_conversation = MagicMock()
        mock_history._conversation = MagicMock()
        mock_history._conversation.value = []

        # Base is 10 but checkpoint only has 3 (shouldn't happen)
        saver._turn_base_count = 10

        msgs = [
            HumanMessage(content="x"),
            AIMessage(content="y"),
            AIMessage(content="z"),
        ]
        checkpoint = _make_checkpoint(msgs)
        metadata = {"source": "update", "step": 3, "parents": {}}

        with patch.object(saver.logger, "warning") as mock_warning:
            saver.put(_make_config("202"), checkpoint, metadata)

        # Should have logged a warning with counts only.
        # logger.warning uses %-formatting, so args[0] is the
        # format string and args[1:] are the interpolated values.
        mock_warning.assert_called_once()
        call_args = mock_warning.call_args[0]
        fmt_string = call_args[0]
        assert "base=" in fmt_string
        assert "checkpoint=" in fmt_string
        # The integer counts are separate positional args.
        assert call_args[1] == 10
        assert call_args[2] == 3
        # No message content in the warning
        for arg in call_args:
            assert "HumanMessage" not in str(arg)
            assert '"x"' not in str(arg)

        # Should not have raised
        assert mock_history.add_message.call_count == 0

    def test_get_tuple_sets_turn_base_count_on_cache_hit(self):
        """get_tuple() sets _turn_base_count from in-memory cache."""
        saver, mock_history = _make_saver(conversation_id=203)
        thread_id = "203"
        msgs = [
            HumanMessage(content="cached"),
            AIMessage(content="reply"),
        ]
        checkpoint = _make_checkpoint(msgs)
        metadata = {"source": "update", "step": 2, "parents": {}}

        saver._checkpoint_state[thread_id] = {
            "checkpoint": checkpoint,
            "metadata": metadata,
            "messages": msgs,
        }

        saver.get_tuple(_make_config(thread_id))

        assert saver._turn_base_count == 2

    def test_get_tuple_sets_turn_base_count_on_db_fallback(self):
        """get_tuple() sets _turn_base_count from DB fallback path."""
        saver, mock_history = _make_saver(conversation_id=204)
        db_messages = [
            HumanMessage(content="from db"),
            AIMessage(content="reply"),
        ]
        mock_history.messages = db_messages

        saver.get_tuple(_make_config("204"))

        assert saver._turn_base_count == 2

    def test_get_tuple_sets_turn_base_count_zero_when_empty(self):
        """get_tuple() sets _turn_base_count=0 when no messages exist."""
        saver, mock_history = _make_saver(conversation_id=205)
        mock_history.messages = []

        saver.get_tuple(_make_config("205"))

        assert saver._turn_base_count == 0

    def test_get_tuple_sets_turn_base_count_zero_in_stateless(self):
        """get_tuple() sets _turn_base_count=0 in stateless mode."""
        saver, _ = _make_saver(conversation_id=206, stateless=True)

        saver.get_tuple(_make_config("206"))

        assert saver._turn_base_count == 0
