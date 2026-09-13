"""Unit tests for the streamed-spacing fix in the daemon.

Regression coverage for plans/uwuchat-streamed-spacing-corruption.md:
``create_streaming_callback`` (generation_signal_support.py) previously ran
every streamed token through ``prepare_stream_chunk``, which inserted a
space at every alnum→alnum chunk boundary and split BPE subword tokens
("air unner", "hugging face"). The fix is plain concatenation — llama.cpp's
native detokenization already emits complete words with real spaces.
"""

from __future__ import annotations

from unittest.mock import Mock

from airunner_services.llm.managers.mixins.generation_signal_support import (
    create_streaming_callback,
)


def _make_owner() -> Mock:
    """Return a minimal owner with the attributes the callback touches."""
    owner = Mock()
    owner._current_request_id = "req-1"
    owner.logger = Mock()
    owner.api.llm.send_llm_text_streamed_signal = Mock()
    owner._workflow_manager = Mock()
    owner._workflow_manager._assistant_turn_index = 0
    return owner


def _collected_messages(owner: Mock) -> list[str]:
    """Return the message texts sent through the streamed-signal mock."""
    messages = []
    for call in owner.api.llm.send_llm_text_streamed_signal.call_args_list:
        response = call.args[0]
        messages.append(getattr(response, "message", ""))
    return messages


def test_subword_boundary_chunks_concatenate_without_spaces() -> None:
    """BPE subword fragments join without a spurious boundary space."""
    owner = _make_owner()
    complete_response: list[str] = [""]
    sequence_counter = [0]
    cb = create_streaming_callback(
        owner, None, complete_response, sequence_counter
    )

    for fragment in ["air", "unner", " ", "res", "olvable"]:
        cb(fragment)

    assert complete_response[0] == "airunner resolvable"


def test_real_word_boundaries_keep_their_spaces() -> None:
    """Chunks that carry their own spaces are preserved verbatim."""
    owner = _make_owner()
    complete_response: list[str] = [""]
    sequence_counter = [0]
    cb = create_streaming_callback(
        owner, None, complete_response, sequence_counter
    )

    for fragment in ["hugging", " face", " ", "works"]:
        cb(fragment)

    # "hugging" + " face" → "hugging face"; " " + "works" → " works".
    assert complete_response[0] == "hugging face works"


def test_first_chunk_preamble_still_stripped() -> None:
    """The leading-assistant-preamble strip is preserved after the fix."""
    owner = _make_owner()
    complete_response: list[str] = [""]
    sequence_counter = [0]
    cb = create_streaming_callback(
        owner, None, complete_response, sequence_counter
    )

    cb("assistant\nairunner")

    assert complete_response[0] == "airunner"


def test_signals_forward_verbatim_fragments() -> None:
    """Each forwarded signal carries the raw fragment, not a re-spaced one."""
    owner = _make_owner()
    complete_response: list[str] = [""]
    sequence_counter = [0]
    cb = create_streaming_callback(
        owner, None, complete_response, sequence_counter
    )

    cb("air")
    cb("unner")

    assert _collected_messages(owner) == ["air", "unner"]
