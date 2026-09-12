"""Integration tests for PII masking in ToolManager + message flow.

Tests the Phase 3 boundary: tool de-mask/re-mask and LangChain message
masking.  No real LLM / network calls — all stubs and mocks.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from airunner_services.llm.pii.masker import mask_langchain_messages
from airunner_services.llm.pii.vault import PIIVault
from airunner_services.llm.tool_manager import (
    _re_mask_value,
    _restore_value,
    ToolManager,
)


# ---------------------------------------------------------------------------
# Tool de-mask / re-mask helpers
# ---------------------------------------------------------------------------


class TestRestoreValue:
    """Tests for ``_restore_value`` (de-mask before tool execution)."""

    def test_restores_placeholder_in_string(self):
        """Placeholder in a string arg is replaced with original."""
        vault = PIIVault()
        vault.placeholder_for("PERSON", "Alice")
        result = _restore_value("Hello [PERSON_1]", vault)
        assert result == "Hello Alice"

    def test_passes_non_string_unchanged(self):
        """Non-string values pass through unchanged."""
        vault = PIIVault()
        assert _restore_value(42, vault) == 42
        assert _restore_value(None, vault) is None


class TestReMaskValue:
    """Tests for ``_re_mask_value`` (re-mask tool return value)."""

    def test_re_masks_known_original(self):
        """Tool result containing a vault original is re-masked."""
        vault = PIIVault()
        vault.placeholder_for("PERSON", "Alice")
        with patch(
            "airunner_services.llm.pii.masker.get_analyzer"
        ) as mock_get:
            mock_get.return_value.analyze.return_value = [
                {"entity_type": "PERSON", "start": 7, "end": 12,
                 "score": 0.85},
            ]
            result = _re_mask_value("Found: Alice's profile", vault)
        assert "Alice" not in result
        assert "[PERSON_1]" in result

    def test_empty_string_unchanged(self):
        """Empty tool result passes through."""
        vault = PIIVault()
        assert _re_mask_value("", vault) == ""


# ---------------------------------------------------------------------------
# ToolManager._execute_tool PII integration
# ---------------------------------------------------------------------------


class TestExecuteToolPII:
    """Verify de-mask before tool call, re-mask on return."""

    def test_de_masks_kwargs_before_tool_call(self):
        """Tool receives real values in kwargs, not placeholders."""
        vault = PIIVault()
        vault.placeholder_for("PERSON", "Alice")

        tm = ToolManager(rag_manager=MagicMock())
        tm.set_active_vault(vault)

        received = {}

        def fake_tool(name: str) -> str:
            received["name"] = name
            return f"Processed: {name}"

        from airunner_services.llm.core.tool_registry import (
            ToolInfo,
        )

        tool_info = ToolInfo(
            name="fake_tool",
            func=fake_tool,
            description="test",
            category=None,
            requires_api=False,
            requires_agent=False,
        )
        with patch(
            "airunner_services.llm.pii.masker.get_analyzer"
        ) as mock_get:
            mock_get.return_value.analyze.return_value = [
                {"entity_type": "PERSON", "start": 11, "end": 16,
                 "score": 0.85},
            ]
            result = tm._execute_tool(
                tool_info,
                (),
                {"name": "[PERSON_1]"},
                {"name"},
                False,
                None,
            )

        assert received["name"] == "Alice"
        assert "Alice" not in str(result)
        assert "[PERSON_1]" in str(result)

    def test_no_vault_passes_through_unchanged(self):
        """Without a vault, tool kwargs and results are untouched."""
        tm = ToolManager(rag_manager=MagicMock())

        def fake_tool(name: str) -> str:
            return f"Hello {name}"

        from airunner_services.llm.core.tool_registry import (
            ToolInfo,
        )

        tool_info = ToolInfo(
            name="fake_tool",
            func=fake_tool,
            description="test",
            category=None,
            requires_api=False,
            requires_agent=False,
        )
        result = tm._execute_tool(
            tool_info,
            (),
            {"name": "[PERSON_1]"},
            {"name"},
            False,
            None,
        )

        assert result == "Hello [PERSON_1]"


# ---------------------------------------------------------------------------
# mask_langchain_messages
# ---------------------------------------------------------------------------


class TestMaskLangChainMessages:
    """Tests for ``mask_langchain_messages``."""

    def test_masks_content_in_messages(self):
        """LangChain message content is masked, other fields preserved."""
        try:
            from langchain_core.messages import (
                HumanMessage,
                SystemMessage,
            )
        except ImportError:
            pytest.skip("langchain_core not available")

        vault = PIIVault()
        messages = [
            SystemMessage(content="You are a helpful assistant."),
            HumanMessage(content="My name is Alice and my email is a@b.com"),
        ]

        def _mock_analyze(text, **kwargs):
            if "Alice" in text:
                return [
                    {"entity_type": "PERSON", "start": 11, "end": 16, "score": 0.85},
                    {"entity_type": "EMAIL_ADDRESS", "start": 31, "end": 38, "score": 0.90},
                ]
            return []

        with patch(
            "airunner_services.llm.pii.masker.get_analyzer"
        ) as mock_get:
            mock_get.return_value.analyze.side_effect = _mock_analyze
            result = mask_langchain_messages(messages, vault)

        assert len(result) == 2
        assert result[0].content == "You are a helpful assistant."
        assert "Alice" not in result[1].content
        assert "a@b.com" not in result[1].content
        assert "[PERSON_1]" in result[1].content
        assert "[EMAIL_ADDRESS_1]" in result[1].content

    def test_does_not_mutate_input_list(self):
        """Original message list is not mutated."""
        try:
            from langchain_core.messages import HumanMessage
        except ImportError:
            pytest.skip("langchain_core not available")

        vault = PIIVault()
        messages = [HumanMessage(content="Hi Alice")]

        def _mock_analyze(text, **kwargs):
            if "Alice" in text:
                return [
                    {"entity_type": "PERSON", "start": 3, "end": 8, "score": 0.85},
                ]
            return []

        with patch(
            "airunner_services.llm.pii.masker.get_analyzer"
        ) as mock_get:
            mock_get.return_value.analyze.side_effect = _mock_analyze
            _ = mask_langchain_messages(messages, vault)

        assert messages[0].content == "Hi Alice"


# ---------------------------------------------------------------------------
# Flag-off: complete no-op
# ---------------------------------------------------------------------------


class TestFlagOff:
    """When PII masking is disabled, everything is a no-op."""

    def test_tool_manager_no_vault_no_change(self):
        """Without set_active_vault, tool passes through args unchanged."""
        tm = ToolManager(rag_manager=MagicMock())

        def fake_tool(query: str) -> str:
            return f"Search: {query}"

        from airunner_services.llm.core.tool_registry import ToolInfo

        tool_info = ToolInfo(
            name="search",
            func=fake_tool,
            description="test",
            category=None,
            requires_api=False,
            requires_agent=False,
        )
        result = tm._execute_tool(
            tool_info,
            (),
            {"query": "Alice"},
            {"query"},
            False,
            None,
        )

        assert result == "Search: Alice"

    def test_settings_defaults_to_off(self):
        """When AIRUNNER_PII_MASKING_ENABLED is not set, it defaults False."""
        import os
        # Ensure the env var is not set during this test.
        old = os.environ.pop("AIRUNNER_PII_MASKING_ENABLED", None)
        try:
            import importlib
            from airunner_services.llm.pii import settings as pii_settings
            importlib.reload(pii_settings)
            assert pii_settings.PII_MASKING_ENABLED is False
        finally:
            if old is not None:
                os.environ["AIRUNNER_PII_MASKING_ENABLED"] = old
            importlib.reload(pii_settings)


# ---------------------------------------------------------------------------
# Fresh PII in tool result (finding #3)
# ---------------------------------------------------------------------------


class TestFreshPIIInToolResult:
    """Tool returns brand-new PII — must be detected and masked."""

    def test_new_email_in_tool_return_is_masked(self):
        """A tool returning an email never seen before is masked."""
        vault = PIIVault()
        vault.placeholder_for("PERSON", "Alice")

        tm = ToolManager(rag_manager=MagicMock())
        tm.set_active_vault(vault)

        def fake_tool(query: str) -> str:
            return "Found: alice@example.com"

        from airunner_services.llm.core.tool_registry import ToolInfo

        tool_info = ToolInfo(
            name="search",
            func=fake_tool,
            description="test",
            category=None,
            requires_api=False,
            requires_agent=False,
        )

        with patch(
            "airunner_services.llm.pii.masker.get_analyzer"
        ) as mock_get:
            mock_get.return_value.analyze.return_value = [
                {"entity_type": "EMAIL_ADDRESS", "start": 7,
                 "end": 23, "score": 0.90},
            ]
            result = tm._execute_tool(
                tool_info, (), {"query": "find Alice"},
                {"query"}, False, None,
            )

        assert "alice@example.com" not in str(result)
        assert "[EMAIL_ADDRESS_1]" in str(result)


# ---------------------------------------------------------------------------
# AIMessage with tool_calls masking (finding #4)
# ---------------------------------------------------------------------------


class TestAIMessageWithToolCalls:
    """``mask_langchain_messages`` preserves tool_calls on AIMessage."""

    def test_aimessage_tool_calls_preserved(self):
        """AIMessage with tool_calls survives masking intact."""
        try:
            from langchain_core.messages import AIMessage
        except ImportError:
            pytest.skip("langchain_core not available")

        vault = PIIVault()
        vault.placeholder_for("PERSON", "Alice")

        msg = AIMessage(
            content="I'll search for Alice",
            tool_calls=[
                {"name": "search", "args": {"query": "Alice"}, "id": "1"},
            ],
        )

        with patch(
            "airunner_services.llm.pii.masker.get_analyzer"
        ) as mock_get:
            mock_get.return_value.analyze.return_value = []
            result = mask_langchain_messages([msg], vault)

        # Content unchanged (no PII detected by mock).
        # Tool calls must be preserved.
        assert hasattr(result[0], "tool_calls")
        assert result[0].tool_calls == msg.tool_calls

    def test_aimessage_content_masked_tool_calls_intact(self):
        """AIMessage content masked; tool_calls untouched."""
        try:
            from langchain_core.messages import AIMessage
        except ImportError:
            pytest.skip("langchain_core not available")

        vault = PIIVault()

        msg = AIMessage(
            content="I'll search for Alice",
            tool_calls=[
                {"name": "search", "args": {"query": "Alice"}, "id": "1"},
            ],
        )

        with patch(
            "airunner_services.llm.pii.masker.get_analyzer"
        ) as mock_get:
            mock_get.return_value.analyze.return_value = [
                {"entity_type": "PERSON", "start": 16, "end": 21,
                 "score": 0.85},
            ]
            result = mask_langchain_messages([msg], vault)

        assert "Alice" not in getattr(result[0], "content", "")
        assert "[PERSON_1]" in getattr(result[0], "content", "")
        assert result[0].tool_calls == msg.tool_calls


# ---------------------------------------------------------------------------
# Real analyzer construction path (finding #1)
# ---------------------------------------------------------------------------


class TestAnalyzerSingleton:
    """Exercise the real _AnalyzerSingleton OSError degrade path."""

    def test_oserror_on_model_load_sets_analyzer_to_none(self):
        """When AnalyzerEngine raises OSError (missing spaCy model),
        _ensure_loaded catches it and sets _analyzer to None."""
        from unittest.mock import MagicMock
        from airunner_services.llm.pii.analyzer import _AnalyzerSingleton

        singleton = _AnalyzerSingleton()
        singleton._loaded = False
        singleton._analyzer = "stale"

        def _raise_oserror(*args, **kwargs):
            raise OSError("[E050] Can't find model 'en_core_web_sm'")

        fake_presidio = MagicMock()
        fake_presidio.AnalyzerEngine = MagicMock(
            side_effect=_raise_oserror,
        )
        with patch.dict(
            "sys.modules", {"presidio_analyzer": fake_presidio}
        ):
            singleton._ensure_loaded()

        assert singleton._loaded is True
        assert singleton._analyzer is None

    def test_analyze_returns_empty_list_when_not_loaded(self):
        """analyze() returns [] when Presidio engines are unavailable."""
        from airunner_services.llm.pii.analyzer import _AnalyzerSingleton

        singleton = _AnalyzerSingleton()
        singleton._loaded = True
        singleton._analyzer = None
        singleton._anonymizer = None
        result = singleton.analyze("Alice lives in Denver")
        assert result == []

    def test_real_presidio_construction_and_analyze(self):
        """When presidio-analyzer + spaCy model are actually installed,
        _ensure_loaded constructs successfully and .analyze() returns
        non-empty results for known PII."""
        pytest.importorskip("presidio_analyzer")
        from airunner_services.llm.pii.analyzer import _AnalyzerSingleton

        singleton = _AnalyzerSingleton()
        singleton._ensure_loaded()

        assert singleton._analyzer is not None, (
            "_analyzer should be non-None when presidio is installed"
        )
        results = singleton.analyze("My name is Alice and I live in Denver")
        assert len(results) > 0, (
            "Expected at least one PII entity in 'My name is Alice "
            "and I live in Denver'"
        )
