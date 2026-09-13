#!/usr/bin/env python3
"""One-shot diagnostic: does OpenRouter stream *content* tokens one-at-a-time?

Makes a raw HTTP streaming POST to OpenRouter's chat/completions endpoint,
bypassing langchain-openai and this app's entire pipeline. Iterates the raw
SSE response line-by-line, printing only event counts, lengths, and
timestamps — never the actual generated text or API key.

Matches the real DIALOGUE path:
  - Model: anthropic/claude-haiku-4.5
  - extra_body.reasoning: {"effort": "medium", "exclude": False}
  - stream: true

Run:  docker compose exec server python server/scripts/diag_openrouter_sse.py

Delete or archive once this one-time question is answered — this is not
wired into the app and should not be treated as a permanent utility.
"""

from __future__ import annotations

import json
import os
import sys
import time

from airunner_services.conf.model_settings import CLAUDE_HAIKU_MODEL


def main() -> None:
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        print("OPENROUTER_API_KEY not set in environment", file=sys.stderr)
        sys.exit(1)

    import httpx

    model = CLAUDE_HAIKU_MODEL
    prompt = (
        "Tell me a short story about a cat who discovers a hidden garden. "
        "Make it at least three paragraphs long."
    )

    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "extra_body": {
            "reasoning": {"effort": "medium", "exclude": False},
        },
    }

    print(f"=== OpenRouter SSE diagnostic ===")
    print(f"Model:  {model}")
    print(f"Prompt: {prompt[:60]}...")
    print()

    reasoning_count = 0
    content_count = 0
    content_lengths: list[int] = []
    t0 = time.monotonic()

    with httpx.stream(
        "POST",
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost",
            "X-Title": "diag_openrouter_sse",
        },
        json=body,
        timeout=120.0,
    ) as resp:
        resp.raise_for_status()
        for raw_line in resp.iter_lines():
            if not raw_line:
                continue
            if not raw_line.startswith("data:"):
                continue
            payload = raw_line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                obj = json.loads(payload)
            except json.JSONDecodeError:
                continue

            choices = obj.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}

            elapsed = time.monotonic() - t0

            # Reasoning / thinking tokens
            reasoning = delta.get("reasoning_content") or delta.get(
                "reasoning",
            )
            if reasoning:
                reasoning_count += 1
                rlen = len(reasoning) if isinstance(reasoning, str) else 0
                print(
                    f"  [{elapsed:7.3f}s] reasoning #{reasoning_count}"
                    f"  len={rlen}",
                )
                continue

            # Visible content tokens
            content = delta.get("content")
            if content:
                content_count += 1
                clen = len(content) if isinstance(content, str) else 0
                content_lengths.append(clen)
                print(
                    f"  [{elapsed:7.3f}s] content   #{content_count}"
                    f"  len={clen}",
                )

    total = time.monotonic() - t0
    print()
    print("=== Summary ===")
    print(f"Total duration:     {total:.3f}s")
    print(f"Reasoning events:   {reasoning_count}")
    print(f"Content events:     {content_count}")
    print(f"Content lengths:    {content_lengths}")
    if content_count == 0:
        print("RESULT: No content events — answer never arrived.")
    elif content_count == 1:
        print(
            "RESULT: Exactly one content event — OpenRouter delivered the "
            "entire answer as a single SSE frame. The coalescing happens "
            "upstream of langchain-openai."
        )
    else:
        print(
            f"RESULT: {content_count} content events — OpenRouter is "
            "delivering visible tokens incrementally. If the app still "
            "shows them all at once, the coalescing is inside "
            "langchain-openai's SSE parsing."
        )


if __name__ == "__main__":
    main()
