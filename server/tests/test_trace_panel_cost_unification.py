"""Unit tests for trace-panel cost unification and mood gating.

Covers:
- _update_and_emit_mood interval gating (turns 1, 6, 11, ...)
- _sum_pipeline_usage / _build_call_chain / cost_by_turn agreement
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch, MagicMock

import pytest


# -- stubs ------------------------------------------------------------------

class _StubChatbot:
    """Minimal chatbot stub for _update_and_emit_mood."""

    def __init__(self, botname: str = "testbot", cid: int = 1) -> None:
        self.botname = botname
        self.id = cid


class _StubWorkflowManager:
    """Minimal workflow-manager stub."""

    def __init__(self, conversation_id: int = 42) -> None:
        self._conversation_id = conversation_id


class _StubConversation:
    """Minimal conversation stub."""

    def __init__(self, session_id: int = 100) -> None:
        self.session_id = session_id
        self.user_data = None


class _StubOwner:
    """Minimal generation-owner stub."""

    def __init__(
        self,
        chatbot: _StubChatbot | None = None,
        wm: _StubWorkflowManager | None = None,
    ) -> None:
        self.chatbot = chatbot or _StubChatbot()
        self._workflow_manager = wm or _StubWorkflowManager()
        self.logger = MagicMock()


# -- helpers ----------------------------------------------------------------

def _make_stub_row(
    call_chain_id: str = "cid-1",
    chatbot_id: int | None = 1,
    model_id: str = "test-model",
    pipeline_key: str = "DIALOGUE",
    inp: int = 100,
    out: int = 50,
    cache: int = 0,
    skipped: bool = False,
    recorded_at: Any = None,
) -> MagicMock:
    """Return a MagicMock mimicking a PipelineTokenUsage row."""
    row = MagicMock()
    row.call_chain_id = call_chain_id
    row.chatbot_id = chatbot_id
    row.model_id = model_id
    row.pipeline_key = pipeline_key
    row.input_tokens = inp
    row.output_tokens = out
    row.cache_read_tokens = cache
    row.skipped = skipped
    row.complexity_score = None
    row.tier_name = None
    row.prompt_char_count = None
    row.response_char_count = None
    row.recorded_at = recorded_at
    return row


# -- Part 1: mood gating ----------------------------------------------------

# The target function uses lazy imports.  Patch the *source* modules
# where those objects live, not the function's own module.

_IS_ENABLED_TARGET = (
    "airunner_services.llm.pipeline_loader.is_enabled"
)
_PIPELINE_CFG_TARGET = (
    "airunner_services.llm.pipeline_loader.pipeline_config"
)
_CONVERSATION_TARGET = (
    "airunner_services.database.models.conversation.Conversation"
)
_COUNT_TURNS_TARGET = (
    "airunner_services.llm.rolling_compressor._count_assistant_turns"
)
_MOOD_SYNC_TARGET = (
    "airunner_services.llm.mood.update_mood_sync"
)


class TestMoodUpdateGating:
    """Verify _update_and_emit_mood respects interval_turns."""

    @pytest.mark.parametrize(
        "turn_count,should_fire",
        [
            (0, True),   # seed turn — fire
            (1, False),  # turn 2
            (2, False),  # turn 3
            (3, False),  # turn 4
            (4, False),  # turn 5
            (5, True),   # turn 6 (5 % 5 == 0) — fire
            (6, False),  # turn 7
            (9, False),  # turn 10
            (10, True),  # turn 11 (10 % 5 == 0) — fire
            (11, False),  # turn 12
            (14, False),  # turn 15
            (15, True),  # turn 16 (15 % 5 == 0) — fire
        ],
    )
    def test_gating_fires_at_correct_turns(
        self, turn_count: int, should_fire: bool
    ) -> None:
        """Mood updates fire at turn 1 (seed) and every interval after.

        Because _update_and_emit_mood() runs BEFORE finalize_generation()
        persists the current turn's assistant message, the actual fire
        sequence is turns 1, 6, 11, 16, ... when interval_turns = 5.
        """
        from airunner_services.llm.managers.mixins.generation_execution_support import (
            _update_and_emit_mood,
        )

        owner = _StubOwner()

        with patch(_IS_ENABLED_TARGET, return_value=True), \
             patch(_PIPELINE_CFG_TARGET,
                   return_value={"interval_turns": 5}), \
             patch(_CONVERSATION_TARGET) as mock_conv_cls, \
             patch(_COUNT_TURNS_TARGET, return_value=turn_count), \
             patch(_MOOD_SYNC_TARGET) as mock_mood:

            mock_conv_cls.objects.get.return_value = _StubConversation()
            _update_and_emit_mood(owner)

            if should_fire:
                mock_mood.assert_called_once()
            else:
                mock_mood.assert_not_called()

    def test_returns_none_when_disabled(self) -> None:
        """Returns None when INTRA_SESSION_MOOD is not enabled."""
        from airunner_services.llm.managers.mixins.generation_execution_support import (
            _update_and_emit_mood,
        )

        owner = _StubOwner()
        with patch(_IS_ENABLED_TARGET, return_value=False):
            result = _update_and_emit_mood(owner)
            assert result is None

    def test_returns_none_when_interval_zero(self) -> None:
        """Returns None when interval_turns <= 0."""
        from airunner_services.llm.managers.mixins.generation_execution_support import (
            _update_and_emit_mood,
        )

        owner = _StubOwner()
        with patch(_IS_ENABLED_TARGET, return_value=True), \
             patch(_PIPELINE_CFG_TARGET,
                   return_value={"interval_turns": 0}):
            result = _update_and_emit_mood(owner)
            assert result is None

    def test_returns_none_when_no_chatbot_name(self) -> None:
        """Returns None when chatbot has no botname."""
        from airunner_services.llm.managers.mixins.generation_execution_support import (
            _update_and_emit_mood,
        )

        owner = _StubOwner(chatbot=_StubChatbot(botname=""))
        with patch(_IS_ENABLED_TARGET, return_value=True), \
             patch(_PIPELINE_CFG_TARGET,
                   return_value={"interval_turns": 5}):
            result = _update_and_emit_mood(owner)
            assert result is None


# -- Part 4: cost unification -----------------------------------------------

_PTU_TARGET = (
    "airunner_services.database.models.pipeline_token_usage"
    ".PipelineTokenUsage"
)
# _sum_pipeline_usage() lazily imports these from token_usage_routes.
_PRICE_LOOKUP_TARGET = (
    "airunner_services.api.routes.token_usage_routes._price_lookup"
)
_COMPUTE_COST_TARGET = (
    "airunner_services.api.routes.token_usage_routes._compute_cost"
)


class TestCostUnification:
    """Verify all cost-aggregation paths return identical results."""

    _PRICES: dict = {
        "test-model": {"input": 0.5, "output": 1.5, "cache": 0.25},
    }

    @staticmethod
    def _stub_compute_cost(
        row: Any, prices: dict, model_id: str
    ) -> float:
        p = prices.get(model_id, {})
        inp = int(getattr(row, "input_tokens", 0) or 0)
        out = int(getattr(row, "output_tokens", 0) or 0)
        cache = int(getattr(row, "cache_read_tokens", 0) or 0)
        return (
            (inp / 1_000_000) * p.get("input", 0)
            + (out / 1_000_000) * p.get("output", 0)
            + (cache / 1_000_000) * p.get("cache", 0)
        )

    def test_sum_pipeline_usage_matches_build_call_chain_totals(
        self,
    ) -> None:
        """_build_call_chain's totals equal _sum_pipeline_usage's."""
        rows = [
            _make_stub_row(inp=100, out=50),
            _make_stub_row(inp=200, out=30,
                           pipeline_key="INTRA_SESSION_MOOD"),
        ]

        from airunner_services.api.routes.call_chain_routes import (
            _sum_pipeline_usage,
        )

        with patch(_PTU_TARGET) as mock_ptu, \
             patch(_PRICE_LOOKUP_TARGET,
                   return_value=self._PRICES), \
             patch(_COMPUTE_COST_TARGET,
                   side_effect=self._stub_compute_cost):
            mock_ptu.objects.query.return_value.filter.return_value.all.return_value = rows

            summary = _sum_pipeline_usage("cid-1")

        assert summary["input_tokens"] == 300
        assert summary["output_tokens"] == 80
        expected_cost = (
            (300 / 1_000_000) * 0.5 + (80 / 1_000_000) * 1.5
        )
        assert summary["cost_usd"] == pytest.approx(expected_cost, 0.000001)

    def test_mixed_chatbot_id_rows_still_agree(self) -> None:
        """Rows with different chatbot_ids for same call_chain_id
        are all summed by _sum_pipeline_usage."""
        rows = [
            _make_stub_row(call_chain_id="cid-x", chatbot_id=1,
                           inp=100, out=50),
            _make_stub_row(call_chain_id="cid-x", chatbot_id=2,
                           inp=30, out=10),
            _make_stub_row(call_chain_id="cid-x", chatbot_id=None,
                           inp=20, out=5, pipeline_key="KNOWLEDGE"),
        ]

        from airunner_services.api.routes.call_chain_routes import (
            _sum_pipeline_usage,
        )

        with patch(_PTU_TARGET) as mock_ptu, \
             patch(_PRICE_LOOKUP_TARGET,
                   return_value=self._PRICES), \
             patch(_COMPUTE_COST_TARGET,
                   side_effect=self._stub_compute_cost):
            mock_ptu.objects.query.return_value.filter.return_value.all.return_value = rows

            summary = _sum_pipeline_usage("cid-x")

        # All three rows summed regardless of chatbot_id
        assert summary["input_tokens"] == 150
        assert summary["output_tokens"] == 65
        assert summary["cost_usd"] > 0


# -- Part 5c: extractor reconciliation --------------------------------------

class TestReconcileExtractorEntries:
    """Verify _reconcile_extractor_entries moves misattributed entries."""

    def test_moves_extractor_entries_to_correct_turn(self) -> None:
        """Turn-1's extractor entries (tagged with turn-1's
        call_chain_id) that land in turn-2's bucket via
        insertion-order partitioning are moved back to turn 1."""
        from extensions.conversation_inspector.server.flow_reconstructor \
            import _reconcile_extractor_entries

        # Simulate 2 turns after _partition_turns().
        # Turn 1's assistant response has call_chain_id "cid-1".
        # Turn 2's assistant response has call_chain_id "cid-2".
        # The extractor for turn 1 wrote 3 metadata entries
        # (2 tool_calls + 1 tool_result) that arrived late and
        # landed in turn 2's bucket.
        turn1: list[dict] = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi!",
             "call_chain_id": "cid-1"},
        ]
        turn2: list[dict] = [
            {"role": "user", "content": "how are you"},
            {"role": "assistant", "content": "good!",
             "call_chain_id": "cid-2"},
            # These 3 belong to turn 1's extractor but arrived late.
            {"metadata_type": "tool_calls",
             "call_chain_id": "cid-1",
             "tool_calls": [{"name": "check_similar_facts"}]},
            {"metadata_type": "tool_result",
             "call_chain_id": "cid-1",
             "content": "no matches"},
            {"metadata_type": "tool_calls",
             "call_chain_id": "cid-1",
             "tool_calls": [{"name": "save_fact"}]},
        ]
        turns = [turn1, turn2]
        cid_to_turn = {"cid-1": 0, "cid-2": 1}

        _reconcile_extractor_entries(turns, cid_to_turn)

        # Turn 1 should now have its own extractor entries.
        assert len(turns[0]) == 5  # user + assistant + 3 extractor
        assert len(turns[1]) == 2  # user + assistant only
        # Turn 1's entries are the 3 extractor metadata rows.
        extractor_rows = turns[0][2:]
        assert extractor_rows[0]["call_chain_id"] == "cid-1"
        assert extractor_rows[1]["call_chain_id"] == "cid-1"
        assert extractor_rows[2]["call_chain_id"] == "cid-1"

    def test_no_op_when_no_misattribution(self) -> None:
        """When all entries are already in the correct turn, nothing
        changes."""
        from extensions.conversation_inspector.server.flow_reconstructor \
            import _reconcile_extractor_entries

        turn1: list[dict] = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi!",
             "call_chain_id": "cid-1"},
            {"metadata_type": "tool_calls",
             "call_chain_id": "cid-1"},
        ]
        turn2: list[dict] = [
            {"role": "user", "content": "bye"},
            {"role": "assistant", "content": "bye!",
             "call_chain_id": "cid-2"},
        ]
        turns = [turn1, turn2]
        cid_to_turn = {"cid-1": 0, "cid-2": 1}

        _reconcile_extractor_entries(turns, cid_to_turn)

        assert len(turns[0]) == 3
        assert len(turns[1]) == 2

    def test_entries_without_call_chain_id_are_untouched(self) -> None:
        """Metadata entries without call_chain_id stay in place."""
        from extensions.conversation_inspector.server.flow_reconstructor \
            import _reconcile_extractor_entries

        turn1: list[dict] = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi!",
             "call_chain_id": "cid-1"},
        ]
        # Live-turn tool calls from the real assistant don't carry
        # call_chain_id (only extractor-authored entries do after
        # Part 5a/b).
        turn2: list[dict] = [
            {"role": "user", "content": "bye"},
            {"role": "assistant", "content": "bye!",
             "call_chain_id": "cid-2"},
            {"metadata_type": "tool_calls",
             "tool_calls": [{"name": "search_web"}]},
        ]
        turns = [turn1, turn2]
        cid_to_turn = {"cid-1": 0, "cid-2": 1}

        _reconcile_extractor_entries(turns, cid_to_turn)

        # Live-turn tool call without call_chain_id stays in turn 2.
        assert len(turns[0]) == 2
        assert len(turns[1]) == 3
