"""Tests for finish_reason truncation detection.

Covers:
- ``_check_truncation`` in the DIALOGUE/RESPONSE streaming path
  (NodeStreamingResponseHelper)
- ``_check_extractor_truncation`` in the KNOWLEDGE extractor path
  (knowledge_extractor module)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage


def _make_aimessage(
    finish_reason: str = "",
    completion_tokens: int = 0,
) -> AIMessage:
    """Return an AIMessage with response_metadata and usage_metadata."""
    return AIMessage(
        content="test",
        response_metadata={
            "finish_reason": finish_reason,
            "token_usage": {
                "completion_tokens": completion_tokens,
                "prompt_tokens": 100,
                "total_tokens": 100 + completion_tokens,
            },
        },
        usage_metadata={
            "output_tokens": completion_tokens,
            "input_tokens": 100,
            "total_tokens": 100 + completion_tokens,
        },
    )


# ---------------------------------------------------------------------------
# _check_truncation (streaming path)
# ---------------------------------------------------------------------------


class TestStreamingTruncationDetection:
    """Verify that the streaming helper's ``_check_truncation`` logs
    distinctly for cut-off vs. natural completion."""

    @staticmethod
    def _make_helper(owner_mock: MagicMock) -> object:
        """Create a NodeStreamingResponseHelper wired to *owner_mock*."""
        from airunner_services.llm.managers.mixins.node_streaming_response_helper import (
            NodeStreamingResponseHelper,
        )
        return NodeStreamingResponseHelper(owner_mock)

    # -- finish_reason == "length" --------------------------------------

    def test_logs_warning_when_finish_reason_is_length(self) -> None:
        """When finish_reason == 'length', _check_truncation must log
        at WARNING with the generation label."""
        owner = MagicMock()
        helper = self._make_helper(owner)

        msg = _make_aimessage(
            finish_reason="length", completion_tokens=500,
        )
        helper._check_truncation(msg, "DIALOGUE (response)")

        owner.logger.warning.assert_called_once()
        text = owner.logger.warning.call_args[0][0]
        assert "[TRUNCATION]" in text
        assert "DIALOGUE (response)" in text
        assert "cut off by max_tokens" in text
        assert "finish_reason='length'" in text
        assert "completion_tokens=500" in text

    def test_includes_completion_tokens_in_warning(self) -> None:
        """The WARNING log line must include the completion_tokens
        count so operators can gauge how badly the response was
        cut off."""
        owner = MagicMock()
        helper = self._make_helper(owner)

        msg = _make_aimessage(
            finish_reason="length", completion_tokens=499,
        )
        helper._check_truncation(msg, "RESPONSE (response)")

        owner.logger.warning.assert_called_once()
        text = owner.logger.warning.call_args[0][0]
        assert "completion_tokens=499" in text

    # -- finish_reason == "stop" ----------------------------------------

    def test_logs_debug_when_finish_reason_is_stop(self) -> None:
        """When finish_reason == 'stop', _check_truncation must log
        at DEBUG indicating natural completion."""
        owner = MagicMock()
        helper = self._make_helper(owner)

        msg = _make_aimessage(
            finish_reason="stop", completion_tokens=300,
        )
        helper._check_truncation(msg, "DIALOGUE (response)")

        owner.logger.warning.assert_not_called()
        owner.logger.debug.assert_called_once()
        text = owner.logger.debug.call_args[0][0]
        assert "[TRUNCATION]" in text
        assert "finished naturally" in text
        assert "finish_reason='stop'" in text

    # -- finish_reason absent / empty -----------------------------------

    def test_logs_nothing_when_finish_reason_is_empty(self) -> None:
        """When finish_reason is absent/empty, no log is emitted."""
        owner = MagicMock()
        helper = self._make_helper(owner)

        msg = _make_aimessage(
            finish_reason="", completion_tokens=100,
        )
        helper._check_truncation(msg, "DIALOGUE (response)")

        owner.logger.warning.assert_not_called()
        owner.logger.debug.assert_not_called()

    def test_handles_none_message_gracefully(self) -> None:
        """When msg is None, no log is emitted (no crash)."""
        owner = MagicMock()
        helper = self._make_helper(owner)

        helper._check_truncation(None, "DIALOGUE (response)")

        owner.logger.warning.assert_not_called()
        owner.logger.debug.assert_not_called()

    def test_handles_message_without_response_metadata(self) -> None:
        """When msg has no response_metadata, no log is emitted."""
        owner = MagicMock()
        helper = self._make_helper(owner)

        msg = AIMessage(content="hello")
        helper._check_truncation(msg, "KNOWLEDGE (tool call)")

        owner.logger.warning.assert_not_called()
        owner.logger.debug.assert_not_called()


# ---------------------------------------------------------------------------
# _check_extractor_truncation (KNOWLEDGE extractor path)
# ---------------------------------------------------------------------------


class TestKnowledgeExtractorTruncationDetection:
    """Verify that ``_check_extractor_truncation`` logs distinctly for
    KNOWLEDGE pipeline cut-off vs. natural completion."""

    def test_logs_warning_when_extractor_finish_reason_is_length(
        self,
    ) -> None:
        """When the KNOWLEDGE extractor hits finish_reason='length',
        a WARNING must be emitted because truncated tool-call JSON
        means silent data corruption."""
        from airunner_services.llm.knowledge_extractor import (
            _check_extractor_truncation,
        )

        msg = _make_aimessage(
            finish_reason="length", completion_tokens=500,
        )
        with patch(
            "airunner_services.llm.knowledge_extractor.logger"
        ) as mock_logger:
            _check_extractor_truncation(msg)

        mock_logger.warning.assert_called_once()
        text = mock_logger.warning.call_args[0][0]
        assert "[EXTRACTOR TRUNCATION]" in text
        assert "finish_reason='length'" in text
        assert "completion_tokens=500" in text
        assert "tool-call arguments may be truncated" in text

    def test_logs_debug_when_extractor_finish_reason_is_stop(
        self,
    ) -> None:
        """When the extractor finishes naturally, a DEBUG line is
        emitted."""
        from airunner_services.llm.knowledge_extractor import (
            _check_extractor_truncation,
        )

        msg = _make_aimessage(
            finish_reason="stop", completion_tokens=200,
        )
        with patch(
            "airunner_services.llm.knowledge_extractor.logger"
        ) as mock_logger:
            _check_extractor_truncation(msg)

        mock_logger.warning.assert_not_called()
        mock_logger.debug.assert_called_once()
        text = mock_logger.debug.call_args[0][0]
        assert "[EXTRACTOR]" in text
        assert "Finished naturally" in text
        assert "finish_reason='stop'" in text

    def test_logs_nothing_when_extractor_finish_reason_empty(
        self,
    ) -> None:
        """Empty finish_reason produces no log output."""
        from airunner_services.llm.knowledge_extractor import (
            _check_extractor_truncation,
        )

        msg = _make_aimessage(finish_reason="")
        with patch(
            "airunner_services.llm.knowledge_extractor.logger"
        ) as mock_logger:
            _check_extractor_truncation(msg)

        mock_logger.warning.assert_not_called()
        mock_logger.debug.assert_not_called()
