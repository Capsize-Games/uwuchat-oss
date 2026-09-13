"""Unit tests for system-message forwarding in _stream_responses.

Verifies that is_system_message=True responses are yielded as
StreamDelta objects regardless of is_end_of_message, fixing the
bug where handle_generation_error's signal (is_end_of_message=False)
was silently dropped.
"""

from __future__ import annotations

from unittest.mock import patch


class _FakeResponse:
    """Minimal response object matching what _stream_responses reads."""

    def __init__(
        self,
        message: str = "",
        is_system_message: bool = False,
        is_end_of_message: bool = False,
    ) -> None:
        self.message = message
        self.is_system_message = is_system_message
        self.is_end_of_message = is_end_of_message


def _make_responses(*responses: _FakeResponse):
    """Yield responses wrapped in the dict format from _iter_responses."""
    for r in responses:
        yield r


def test_system_message_not_dropped_when_not_complete() -> None:
    """is_system_message=True + is_end_of_message=False must yield a delta.

    Before the fix, _stream_responses would ``continue`` past
    non-complete system messages, silently dropping them.  After the
    fix, the delta is yielded with message_type="system" and
    final=False.
    """
    from airunner_services.runtimes.local_fallback._llm_client import (
        LocalFallbackLLMClient,
    )
    from airunner_services.ipc.messages import StreamDelta

    # A non-complete system message followed by a normal
    # completion signal — the realistic sequence when
    # handle_generation_error sends is_end_of_message=False
    # and then the stream ends normally.
    fake = _FakeResponse(
        message="Error: Connection error.",
        is_system_message=True,
        is_end_of_message=False,
    )
    done = _FakeResponse(
        message="",
        is_system_message=False,
        is_end_of_message=True,
    )

    client = LocalFallbackLLMClient.__new__(LocalFallbackLLMClient)
    client._timeout_seconds = 5
    with patch.object(
        client,
        "_iter_responses",
        return_value=iter([fake, done]),
    ):
        deltas = list(
            client._stream_responses("req-1", None)  # type: ignore[arg-type]
        )
        # We get the system delta first, then the normal completion.
        assert len(deltas) == 2
        system_delta: StreamDelta = deltas[0]
        assert system_delta.final is False
        assert system_delta.metadata.get("message_type") == "system"
        assert "Connection error" in system_delta.delta.get(
            "content", ""
        )
        assert deltas[1].final is True


def test_system_message_when_complete() -> None:
    """is_system_message=True + is_end_of_message=True must yield a delta.

    This is the path that already worked before the fix — the test
    ensures it was not broken by the change.
    """
    from airunner_services.runtimes.local_fallback._llm_client import (
        LocalFallbackLLMClient,
    )
    from airunner_services.ipc.messages import StreamDelta

    fake = _FakeResponse(
        message="Service unavailable.",
        is_system_message=True,
        is_end_of_message=True,
    )

    client = LocalFallbackLLMClient.__new__(LocalFallbackLLMClient)
    client._timeout_seconds = 5
    with patch.object(
        client,
        "_iter_responses",
        return_value=iter([fake]),
    ):
        deltas = list(
            client._stream_responses("req-1", None)  # type: ignore[arg-type]
        )
        assert len(deltas) == 1
        delta: StreamDelta = deltas[0]
        assert delta.final is True
        assert delta.metadata.get("message_type") == "system"
        assert "Service unavailable" in delta.delta.get("content", "")


def test_system_message_among_normal_chunks() -> None:
    """System message interleaved with normal chunks must yield all."""
    from airunner_services.runtimes.local_fallback._llm_client import (
        LocalFallbackLLMClient,
    )

    responses = [
        _FakeResponse(message="Hello", is_end_of_message=False),
        _FakeResponse(
            message="Error: Connection error.",
            is_system_message=True,
            is_end_of_message=False,
        ),
        _FakeResponse(message=" world", is_end_of_message=True),
    ]

    client = LocalFallbackLLMClient.__new__(LocalFallbackLLMClient)
    client._timeout_seconds = 5
    with patch.object(
        client,
        "_iter_responses",
        return_value=iter(responses),
    ):
        deltas = list(
            client._stream_responses("req-1", None)  # type: ignore[arg-type]
        )
        assert len(deltas) == 3
        assert deltas[0].metadata.get("message_type") != "system"
        assert deltas[1].metadata.get("message_type") == "system"
        assert deltas[2].metadata.get("message_type") != "system"
        assert deltas[2].final is True
