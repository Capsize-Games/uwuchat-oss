"""Tests for null call_chain_id, summarization ordering, and
admin_events timestamp parsing fixes.

Covers:
- sync_request_scope_to_workflow_manager propagates _call_chain_id
- do_generate finalizes response before summarization
- _parse_iso_datetime handles ISO-8601-with-Z timestamps
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch



# ------------------------------------------------------------------
# Issue 1: sync_request_scope_to_workflow_manager propagates
#          _call_chain_id to WorkflowManager
# ------------------------------------------------------------------


class TestSyncCallChainIdPropagation:
    """sync_request_scope_to_workflow_manager sets _call_chain_id
    on the workflow manager when the LLM manager has one."""

    def test_propagates_call_chain_id(self) -> None:
        """When owner has _call_chain_id, it is set on the
        workflow manager via setattr."""
        from airunner_services.llm.managers.mixins.generation_workflow_support import (
            sync_request_scope_to_workflow_manager,
        )

        owner = MagicMock()
        owner._workflow_manager = MagicMock()
        owner._call_chain_id = "test-chain-123"
        owner._current_request_id = "req-1"

        # set_request_id attribute → use setter path
        del owner._workflow_manager.set_request_id

        sync_request_scope_to_workflow_manager(owner)

        assert (
            owner._workflow_manager._call_chain_id == "test-chain-123"
        )

    def test_no_call_chain_id_does_not_set(self) -> None:
        """When owner has no _call_chain_id, nothing is set on
        the workflow manager.

        Uses a real object (not MagicMock) so attribute access
        behaves naturally and _call_chain_id is genuinely absent.
        """
        from airunner_services.llm.managers.mixins.generation_workflow_support import (
            sync_request_scope_to_workflow_manager,
        )

        class StubOwner:
            """Minimal stub with only the attributes the function reads."""

            def __init__(self) -> None:
                self._workflow_manager = StubWorkflowManager()
                self._current_request_id = "req-1"
                # _call_chain_id deliberately absent

        class StubWorkflowManager:
            pass

        owner = StubOwner()
        sync_request_scope_to_workflow_manager(owner)

        assert not hasattr(
            owner._workflow_manager, "_call_chain_id"
        )

    def test_no_workflow_manager_does_not_crash(self) -> None:
        """When owner has no _workflow_manager, the function
        returns early without error."""
        from airunner_services.llm.managers.mixins.generation_workflow_support import (
            sync_request_scope_to_workflow_manager,
        )

        owner = MagicMock()
        owner._workflow_manager = None

        # Should not raise
        sync_request_scope_to_workflow_manager(owner)

    def test_set_request_id_path_propagates_call_chain(self) -> None:
        """When workflow manager has set_request_id, _call_chain_id
        is still propagated via setattr."""
        from airunner_services.llm.managers.mixins.generation_workflow_support import (
            sync_request_scope_to_workflow_manager,
        )

        owner = MagicMock()
        owner._workflow_manager = MagicMock()
        owner._workflow_manager.set_request_id = MagicMock()
        owner._call_chain_id = "chain-via-setter"
        owner._current_request_id = "req-2"

        sync_request_scope_to_workflow_manager(owner)

        assert (
            owner._workflow_manager._call_chain_id
            == "chain-via-setter"
        )
        owner._workflow_manager.set_request_id.assert_called_once_with(
            "req-2"
        )


# ------------------------------------------------------------------
# Issue 2: do_generate ordering — finalize_generation runs before
#          maybe_summarize_checkpoint
# ------------------------------------------------------------------
#
# Audit finding (2026-07-28):
#
# result["messages"] is built in _stream_messages (line 310–327) by
# iterating over workflow_manager.stream() and appending each yielded
# AIMessage to a plain Python list.  _compress_checkpoint replaces
# state["messages"] with a new list (state["messages"] = new_messages)
# — it does NOT mutate the individual AIMessage objects that
# result["messages"] holds references to.  Because Python object
# references are reference-counted, the AIMessage objects in
# result["messages"] remain live and unmodified regardless of what
# summarization does to the checkpoint state dict.
#
# The original bug ("Final AIMessage was empty") therefore had a
# different root cause than checkpoint corruption of result["messages"].
# The reordering fix (finalize BEFORE summarization) is still the
# correct defensive measure: it guarantees no subtle interaction
# between checkpoint rewriting and response extraction can ever occur,
# and it keeps the blocking summarization call out of the critical
# path between stream completion and response delivery.
#


class TestGenerationOrdering:
    """do_generate finalizes the visible response before running
    conversation summarization."""

    def test_result_messages_survive_checkpoint_rewrite(self) -> None:
        """Construct a result dict mirroring what run_generation_stream
        returns, simulate summarization rewriting the checkpoint state
        with _compress_checkpoint, then confirm extract_final_response
        still sees the original text — proving result["messages"] is
        independent of checkpoint mutation.
        """
        from langchain_core.messages import AIMessage

        from airunner_services.llm.managers.mixins.conversation_summarization import (
            _compress_checkpoint,
        )
        from airunner_services.llm.managers.mixins.generation_response_support import (
            extract_final_response,
        )

        # -- Build a result dict matching the real stream output shape
        final_ai = AIMessage(
            content="Here are 50 articles about the topic.",
            tool_calls=[],
        )
        result = {
            "messages": [final_ai],
            "raw_messages": [final_ai],
        }

        # -- Build a checkpoint state matching the shape
        #    _compress_checkpoint expects (conversation_summarization.py
        #    lines 84–111: state is a dict with "messages" and
        #    "checkpoint" / channel_values).
        state_messages = [final_ai]
        state = {
            "messages": state_messages,
            "checkpoint": {
                "channel_values": {"messages": state_messages},
            },
        }
        ckpt_state = {"thread-1": state}

        owner = MagicMock()
        owner.logger = MagicMock()

        # -- Simulate what maybe_summarize_checkpoint does: compress
        #    the checkpoint state between stream completion and
        #    response finalization.
        _compress_checkpoint(
            messages=list(state_messages),
            threshold=1,
            summary="Compressed earlier messages",
            state=state,
            ckpt_state=ckpt_state,
            thread_id="thread-1",
            owner=owner,
        )

        # -- Now extract the final response from result (what
        #    finalize_generation does).  It must still see the
        #    original text, not an empty string.
        extracted = extract_final_response(owner, result)
        assert extracted == "Here are 50 articles about the topic.", (
            f"Expected original text, got {extracted!r}"
        )

    def test_finalize_before_summarize_in_source_order(self) -> None:
        """Structural guard: in do_generate() source the call to
        maybe_summarize_checkpoint appears AFTER finalize_generation.

        This catches accidental reversion of the reordering fix.
        The behavioral test above proves independence; this guard
        ensures the ordering stays correct in source."""
        import inspect

        from airunner_services.llm.managers.mixins.generation_execution_support import (
            do_generate,
        )

        source = inspect.getsource(do_generate)
        finalize_idx = source.find("finalize_generation")
        summarize_idx = source.find("maybe_summarize_checkpoint")

        assert finalize_idx >= 0, (
            "finalize_generation not found in do_generate source"
        )
        assert summarize_idx >= 0, (
            "maybe_summarize_checkpoint not found in do_generate"
        )
        assert finalize_idx < summarize_idx, (
            "finalize_generation must appear BEFORE "
            "maybe_summarize_checkpoint in do_generate source"
        )


# ------------------------------------------------------------------
# Issue 3: _parse_iso_datetime handles ISO-8601-with-Z timestamps
# ------------------------------------------------------------------


class TestParseIsoDatetime:
    """_parse_iso_datetime correctly parses timestamps and rejects
    malformed values with None (caller produces 400)."""

    def test_parses_standard_iso(self) -> None:
        """A standard ISO-8601 datetime without Z suffix."""
        from airunner_services.api.routes.admin_events import (
            _parse_iso_datetime,
        )

        result = _parse_iso_datetime("2026-07-06T13:06:25")
        assert result == datetime(2026, 7, 6, 13, 6, 25)

    def test_parses_iso_with_z_suffix(self) -> None:
        """ISO-8601 with trailing Z (UTC indicator)."""
        from airunner_services.api.routes.admin_events import (
            _parse_iso_datetime,
        )

        result = _parse_iso_datetime("2026-07-06T13:06:25.932Z")
        assert result == datetime(
            2026, 7, 6, 13, 6, 25, 932000, tzinfo=timezone.utc
        )

    def test_parses_iso_with_offset(self) -> None:
        """ISO-8601 with explicit +00:00 offset."""
        from airunner_services.api.routes.admin_events import (
            _parse_iso_datetime,
        )

        result = _parse_iso_datetime(
            "2026-07-06T13:06:25+00:00"
        )
        assert result == datetime(
            2026, 7, 6, 13, 6, 25, tzinfo=timezone.utc
        )

    def test_parses_iso_with_fractional_seconds_and_z(self) -> None:
        """ISO-8601 with microseconds and Z suffix."""
        from airunner_services.api.routes.admin_events import (
            _parse_iso_datetime,
        )

        result = _parse_iso_datetime(
            "2026-01-15T08:30:00.123456Z"
        )
        assert result == datetime(
            2026, 1, 15, 8, 30, 0, 123456, tzinfo=timezone.utc
        )

    def test_none_input_returns_none(self) -> None:
        """None input returns None (no filter applied)."""
        from airunner_services.api.routes.admin_events import (
            _parse_iso_datetime,
        )

        assert _parse_iso_datetime(None) is None

    def test_empty_string_returns_none(self) -> None:
        """Empty string returns None."""
        from airunner_services.api.routes.admin_events import (
            _parse_iso_datetime,
        )

        assert _parse_iso_datetime("") is None

    def test_whitespace_only_returns_none(self) -> None:
        """Whitespace-only string returns None."""
        from airunner_services.api.routes.admin_events import (
            _parse_iso_datetime,
        )

        assert _parse_iso_datetime("   ") is None

    def test_malformed_string_returns_none(self) -> None:
        """Garbage input returns None (caller returns 400)."""
        from airunner_services.api.routes.admin_events import (
            _parse_iso_datetime,
        )

        assert _parse_iso_datetime("not-a-date") is None

    def test_non_string_input_returns_none(self) -> None:
        """Non-string input (e.g. int) returns None."""
        from airunner_services.api.routes.admin_events import (
            _parse_iso_datetime,
        )

        assert _parse_iso_datetime(12345) is None  # type: ignore[arg-type]


# ------------------------------------------------------------------
# Integration: _record_iteration_usage uses fallback
# ------------------------------------------------------------------


class TestRecordIterationUsageFallback:
    """_record_iteration_usage falls back to get_active_call_chain
    when _call_chain_id is not on self._owner."""

    def test_falls_back_to_context_var(self) -> None:
        """When _call_chain_id is absent, get_active_call_chain
        is called as fallback."""
        from airunner_services.llm.managers.mixins.node_prompt_assembly_helper import (
            NodePromptAssemblyHelper,
        )

        owner = MagicMock()
        owner._chat_model = MagicMock()
        owner._chat_model.model = "test/model"
        owner.logger = MagicMock()
        # Explicitly set _call_chain_id to None so the first lookup
        # returns None and the code falls through to the
        # get_active_call_chain() fallback.
        owner._call_chain_id = None

        helper = NodePromptAssemblyHelper(owner)

        response = MagicMock()
        response.usage_metadata = {
            "input_tokens": 10,
            "output_tokens": 20,
        }

        # All imports inside _record_iteration_usage are local
        # function-body imports — patch them at their definition
        # sites, not in the importing module.
        with patch(
            "airunner_services.llm.token_usage.record_usage",
        ) as mock_record, patch(
            "airunner_services.llm.pipeline_loader.pipeline_config",
            return_value={"model": "test/model"},
        ), patch(
            "airunner_services.data.tenant.get_tenant_key",
            return_value="test-tenant",
        ), patch(
            "airunner_services.llm.managers.mixins.generation_usage."
            "cache_read_tokens_from_usage",
            return_value=0,
        ), patch(
            "airunner_services.llm.active_call_chain."
            "get_active_call_chain",
            return_value="ctxvar-chain-456",
        ):
            helper._record_iteration_usage(response, 0)

        call_kwargs = mock_record.call_args.kwargs
        assert call_kwargs["call_chain_id"] == "ctxvar-chain-456"
