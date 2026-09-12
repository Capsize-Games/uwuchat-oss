#!/usr/bin/env python3
"""Diagnostic: trace chunk count through langchain-openai's ChatOpenAI.stream().

Makes a call through the **exact same model constructor** the real
DIALOGUE pipeline uses (`create_openrouter_model()`), then iterates the
.stream() generator and records a timestamp + content length for every
yielded chunk — no text content is logged (only lengths, same as the
Round 3 wire-level script).

Compares the langchain-openai chunk count against the known wire-level
count (156 SSE frames from server/scripts/diag_openrouter_sse.py) to
determine whether langchain-openai is batching the upstream events.

Also tests `extra_body.reasoning` (the parameter our pipeline injects
via `_normalize_stream_kwargs`) to confirm whether it affects chunk
granularity.

Run:  docker compose exec server python server/scripts/diag_langchain_stream.py
"""

from __future__ import annotations

import os
import sys
import time

# ── LangChain imports ──────────────────────────────────────────────
from langchain_core.messages import HumanMessage, SystemMessage
from airunner_services.conf.model_settings import CLAUDE_HAIKU_MODEL


def main() -> None:
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        print("OPENROUTER_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    # Use the EXACT same builder as the app
    from airunner_services.cloud.llm.model_builders import (
        create_openrouter_model,
    )

    model_name = CLAUDE_HAIKU_MODEL
    prompt = (
        "Tell me a short story about a cat who discovers a hidden "
        "garden. Make it at least three paragraphs long."
    )

    # Build a LangChain message list (matching the app's prompt shape)
    messages = [
        SystemMessage(
            content="You are a helpful assistant. Be concise."
        ),
        HumanMessage(content=prompt),
    ]

    # ── Test 1: no extra_body (baseline) ────────────────────────
    print("=" * 60)
    print("Test 1: Baseline (no extra_body)")
    print("=" * 60)
    run_stream_test(create_openrouter_model, api_key, model_name, messages)

    # ── Test 2: with extra_body.reasoning (matching real pipeline) ──
    print()
    print("=" * 60)
    print("Test 2: extra_body.reasoning (effort=medium, exclude=False)")
    print("=" * 60)
    run_stream_test(
        create_openrouter_model,
        api_key,
        model_name,
        messages,
        extra_body={"reasoning": {"effort": "medium", "exclude": False}},
    )


def run_stream_test(
    builder,
    api_key: str,
    model_name: str,
    messages,
    extra_body: dict | None = None,
) -> None:
    """Create a model, stream a response, and report chunk statistics."""
    t0 = time.monotonic()

    model = builder(
        api_key=api_key,
        model_name=model_name,
        temperature=0.7,
        max_tokens=500,
    )

    # Build stream kwargs — if extra_body is requested, inject it into
    # the model_kwargs dict that ChatOpenAI forwards to the API call.
    # This matches how _normalize_stream_kwargs injects reasoning params.
    stream_kwargs: dict = {}
    if extra_body:
        stream_kwargs["extra_body"] = extra_body

    chunks = []
    first_chunk_at: float | None = None
    prev_at: float | None = None

    for chunk in model.stream(messages, **stream_kwargs):
        now = time.monotonic()
        if first_chunk_at is None:
            first_chunk_at = now
        gap = (now - prev_at) * 1000 if prev_at is not None else 0
        prev_at = now

        # Extract content text from the AIMessageChunk
        msg = getattr(chunk, "message", chunk)
        text = getattr(msg, "content", "") or ""
        reasoning = ""
        addl = getattr(msg, "additional_kwargs", {}) or {}
        reasoning = (
            addl.get("reasoning_content")
            or addl.get("reasoning")
            or ""
        )

        chunks.append({
            "idx": len(chunks) + 1,
            "elapsed_ms": (now - t0) * 1000,
            "gap_ms": gap,
            "text_len": len(text) if text else 0,
            "reasoning_len": len(reasoning) if reasoning else 0,
            "has_tool_calls": bool(getattr(msg, "tool_calls", None)),
        })

    total_ms = (time.monotonic() - t0) * 1000

    # ── Statistics ───────────────────────────────────────────────
    text_chunks = [c for c in chunks if c["text_len"] > 0]
    reasoning_chunks = [c for c in chunks if c["reasoning_len"] > 0]
    tool_chunks = [c for c in chunks if c["has_tool_calls"]]

    print(f"Total chunks:          {len(chunks)}")
    print(f"  With text content:   {len(text_chunks)}")
    print(f"  With reasoning:      {len(reasoning_chunks)}")
    print(f"  With tool_calls:     {len(tool_chunks)}")
    print(f"  Empty/null chunks:   {len(chunks) - len(text_chunks) - len(reasoning_chunks)}")
    print(f"First chunk at:        {first_chunk_at and (first_chunk_at - t0) * 1000:.0f}ms")
    print(f"Total wall time:       {total_ms:.0f}ms")

    if text_chunks:
        lengths = [c["text_len"] for c in text_chunks]
        print(f"Text chunk lengths:    min={min(lengths)} max={max(lengths)} avg={sum(lengths)/len(lengths):.1f}")
        # Group gap distribution
        gaps = [c["gap_ms"] for c in text_chunks[1:]]
        if gaps:
            print(f"Inter-chunk gaps:      min={min(gaps):.1f}ms max={max(gaps):.1f}ms avg={sum(gaps)/len(gaps):.1f}ms")

    # Show first 5 and last 5 text chunks for pattern analysis
    if text_chunks:
        print()
        print("First 5 text chunks:")
        for c in text_chunks[:5]:
            print(f"  #{c['idx']:3d}  gap={c['gap_ms']:7.1f}ms  text_len={c['text_len']}")
        if len(text_chunks) > 10:
            print("  ...")
            print(f"Last 5 text chunks:")
            for c in text_chunks[-5:]:
                print(f"  #{c['idx']:3d}  gap={c['gap_ms']:7.1f}ms  text_len={c['text_len']}")

    # Decision
    print()
    if len(text_chunks) <= 5:
        print(
            "RESULT: ≤5 text chunks — langchain-openai is heavily "
            "batching the 156 wire-level SSE frames."
        )
    elif len(text_chunks) < 50:
        print(
            f"RESULT: {len(text_chunks)} text chunks — langchain-openai "
            "is moderately batching the 156 wire-level SSE frames "
            f"(~{156/len(text_chunks):.0f}x reduction)."
        )
    else:
        print(
            f"RESULT: {len(text_chunks)} text chunks — close to "
            "the 156 wire-level frames. langchain-openai is NOT "
            "the bottleneck."
        )


if __name__ == "__main__":
    main()
