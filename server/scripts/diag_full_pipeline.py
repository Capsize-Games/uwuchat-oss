#!/usr/bin/env python3
"""End-to-end diagnostic: count callbacks through the full stream pipeline.

Creates an OpenRouter model, streams a response, and processes every
chunk through the *actual* `_process_chunk` / `store_visible_text` /
`_token_callback` chain that the real DIALOGUE pipeline uses. Counts:

1. Total chunks from chat_model.stream()            [langchain]
2. Chunks with non-empty text content               [langchain]
3. Calls to _token_callback (what the WS would get) [our pipeline]

If #3 is substantially lower than #2, the bottleneck is in
_process_chunk (thinking helper, filter_tool_markup, etc.).

Run:  docker compose exec server python server/scripts/diag_full_pipeline.py
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from airunner_services.conf.model_settings import CLAUDE_HAIKU_MODEL


@dataclass
class FakeStreamingState:
    """Minimal StreamingState for _process_chunk / store_visible_text."""

    streamed_content: list[str] = field(default_factory=list)
    has_streamed_content: bool = False
    in_thinking_block: bool = False
    thinking_started: bool = False
    using_reasoning_deltas: bool = False
    thinking_content: list[str] = field(default_factory=list)
    final_thinking_content: Optional[str] = None
    thinking_tag_format: Optional[str] = None
    in_tool_call_tag: bool = False
    last_chunk_message: Any = None
    last_usage_metadata: Any = None
    accumulated_message: Any = None
    collected_tool_calls: list = field(default_factory=list)


class FakeEventSink:
    """No-op event sink."""

    def emit_stream_reset(self, request_id):
        pass

    def emit_thinking(self, payload):
        pass

    def emit_bot_mood(self, payload):
        pass


class FakeOwner:
    """Minimal owner for _process_chunk / store_visible_text."""

    def __init__(self, callback: Callable[[str], None]):
        self._token_callback = callback
        self.logger = _null_logger()
        self._owner = self  # for thinking helper

    def _store_visible_text(self, state, request_id, text, forward_to_callback=True):
        """Forward to the real store_visible_text."""
        from airunner_services.llm.managers.mixins.node_streaming_response_helpers import (
            store_visible_text,
        )
        store_visible_text(state, self, request_id, text,
                           forward_to_callback=forward_to_callback)


def _null_logger():
    import logging
    log = logging.getLogger("diag_null")
    log.addHandler(logging.NullHandler())
    log.propagate = False
    return log


def main() -> None:
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        print("OPENROUTER_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    from airunner_services.cloud.llm.model_builders import (
        create_openrouter_model,
    )
    from langchain_core.messages import HumanMessage, SystemMessage

    model_name = CLAUDE_HAIKU_MODEL
    prompt = (
        "Tell me a short story about a cat who discovers a hidden "
        "garden. Make it at least three paragraphs long."
    )
    messages = [
        SystemMessage(content="You are a helpful assistant. Be concise."),
        HumanMessage(content=prompt),
    ]

    # We test BOTH with and without reasoning extra_body, to match
    # the real pipeline's _normalize_stream_kwargs behavior.
    for label, extra_body in [
        ("no extra_body", None),
        ("extra_body.reasoning", {"reasoning": {"effort": "medium",
                                                  "exclude": False}}),
    ]:
        print("=" * 60)
        print(f"Test: {label}")
        print("=" * 60)
        run_test(create_openrouter_model, api_key, model_name, messages,
                 extra_body)


def run_test(builder, api_key, model_name, messages, extra_body):
    """Run one test and report callback statistics."""
    t0 = time.monotonic()

    model = builder(
        api_key=api_key,
        model_name=model_name,
        temperature=0.7,
        max_tokens=500,
    )

    stream_kwargs: dict = {}
    if extra_body:
        stream_kwargs["extra_body"] = extra_body

    # ── Callback counters ──────────────────────────────────────
    langchain_chunks = 0
    text_chunks = 0
    callback_calls = 0
    callback_text_lens: list[int] = []
    callback_timestamps: list[float] = []

    def token_callback(text: str) -> None:
        nonlocal callback_calls
        callback_calls += 1
        callback_text_lens.append(len(text))
        callback_timestamps.append(time.monotonic() - t0)

    owner = FakeOwner(callback=token_callback)
    from airunner_services.llm.managers.mixins.node_streaming_thinking_helper import (
        NodeStreamingThinkingHelper,
    )

    thinking_helper = NodeStreamingThinkingHelper(owner)
    event_sink = FakeEventSink()
    state = FakeStreamingState()
    request_id = "diag-test"

    # Import helpers used by _process_chunk
    from airunner_services.llm.managers.mixins.node_streaming_response_helpers import (
        accumulate_chunk,
        filter_tool_markup,
        store_visible_text,
    )

    for chunk in model.stream(messages, **stream_kwargs):
        langchain_chunks += 1
        chunk_message = getattr(chunk, "message", chunk)
        text = getattr(chunk_message, "content", "") or ""
        additional_kwargs = (
            getattr(chunk_message, "additional_kwargs", {}) or {}
        )
        reasoning_delta = (
            additional_kwargs.get("thinking_content")
            or additional_kwargs.get("reasoning_content")
            or additional_kwargs.get("reasoning")
        )
        chunk_tool_calls = getattr(chunk_message, "tool_calls", None)
        usage = getattr(chunk_message, "usage_metadata", None)
        if usage is not None:
            state.last_usage_metadata = usage

        if text:
            text_chunks += 1

        state.last_chunk_message = chunk_message
        accumulate_chunk(state, chunk_message)

        if not text and not chunk_tool_calls and not reasoning_delta:
            continue

        # ---- THIS IS THE ACTUAL _process_chunk LOGIC ----
        th = thinking_helper
        if th.handle_reasoning_delta(
            state, request_id, event_sink, reasoning_delta, text
        ):
            continue
        if th.handle_thinking_open(state, request_id, event_sink, text):
            continue
        if state.in_thinking_block:
            th.handle_thinking_block(state, request_id, event_sink, text)
            continue
        text_to_stream = filter_tool_markup(state, text)
        if text_to_stream:
            store_visible_text(state, owner, request_id, text_to_stream)
        # ---- END _process_chunk LOGIC ----

    total_ms = (time.monotonic() - t0) * 1000

    print(f"Langchain chunks:              {langchain_chunks}")
    print(f"  Chunks with text content:     {text_chunks}")
    print(f"  _token_callback calls:        {callback_calls}")
    print(f"  Callback text lens:           {callback_text_lens[:5]}...")
    print(f"  Total wall time:              {total_ms:.0f}ms")

    lost = text_chunks - callback_calls
    if lost == 0:
        print("RESULT: 1:1 — every text chunk reaches _token_callback.")
        print("  The bottleneck is NOT in _process_chunk.")
        print("  Check: signal mediator queue, WS send loop, or client-side.")
    else:
        print(f"RESULT: {lost} text chunks LOST in _process_chunk.")
        print("  The thinking helper or filter_tool_markup is discarding")
        print("  content that should be forwarded to the client.")
        print(f"  streamed_content length: {len(state.streamed_content)}")

    print()


if __name__ == "__main__":
    main()
