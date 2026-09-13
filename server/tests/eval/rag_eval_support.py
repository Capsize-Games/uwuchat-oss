"""API-backed eval helpers for Docker-based LLM agent eval tests.

This module replaces ``agent_eval_support.py`` with helpers that
communicate with the AI Runner API server (running in Docker) via:

* WebSocket ``/api/v1/llm/stream`` for LLM chat / completion
* WebSocket ``/api/v1/events`` for RPC calls (KB docs, conversations)
* HTTP ``/health`` for health checks

Key differences from the old ``agent_eval_support.py``:

* No local daemon subprocess — talks to the running Docker API server.
* No local model artifact checks — the API manages models.
* Uses the same WebSocket protocol as the real React client.
* Manages RAG documents through the KB API endpoints.
* Does NOT require ``pytest`` at module level — uses ``EvalError``
  for test failures so the module is importable outside pytest.
"""

from __future__ import annotations

import asyncio
import json
import os
import re as _re
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import websockets


class EvalError(Exception):
    """Raised when an eval helper encounters a test-failing condition."""


# ── Configuration ──────────────────────────────────────────────────────────


def _api_host() -> str:
    """Return the API host from env or default."""
    return os.environ.get("AIRUNNER_API_HOST", "localhost")


def _api_port() -> int:
    """Return the API port from env or default."""
    return int(os.environ.get("AIRUNNER_API_PORT", "8080"))


def _ws_base_url() -> str:
    """Return the WebSocket base URL."""
    return f"ws://{_api_host()}:{_api_port()}"


def _http_base_url() -> str:
    """Return the HTTP base URL."""
    return f"http://{_api_host()}:{_api_port()}"


def _eval_timeout() -> float:
    """Return the eval request timeout in seconds."""
    return float(os.environ.get("AIRUNNER_EVAL_TIMEOUT", "300"))


# ── Data types ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EvalResult:
    """Collected response data for one API-backed eval case."""

    status_code: int
    payload: dict[str, Any]
    visible_message: str
    tools: list[str]


@dataclass
class StreamCollector:
    """Accumulates a streaming LLM response from the WebSocket.

    Handles qwen3-style thinking mode where the model outputs its
    reasoning as ``type=thinking`` chunks and the final answer as
    ``type=chunk`` chunks.  When the final chunk is empty, falls
    back to the assembled thinking content.
    """

    chunks: list[str] = field(default_factory=list)
    thinking_chunks: list[str] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    final: bool = False
    error: str | None = None
    full_message: str = ""

    def append_chunk(self, content: str) -> None:
        """Append one text chunk (actual response, not thinking)."""
        self.chunks.append(content)

    def append_thinking(self, content: str) -> None:
        """Append one thinking/reasoning chunk."""
        self.thinking_chunks.append(content)

    def add_tool_calls(self, calls: list[dict]) -> None:
        """Record tool call metadata."""
        self.tool_calls.extend(calls)

    @property
    def text(self) -> str:
        """Return the assembled response text.

        Falls back to thinking content if no explicit response
        chunks were received (qwen3 thinking mode).
        """
        joined = "".join(self.chunks).strip()
        if joined:
            return joined
        return "".join(self.thinking_chunks).strip()

    @property
    def tool_names(self) -> list[str]:
        """Return tool names extracted from tool call metadata."""
        seen: dict[str, bool] = {}
        names: list[str] = []
        for call in self.tool_calls:
            name = call.get("name", "")
            if name and name not in seen:
                seen[name] = True
                names.append(name)
        return names


# ── Health / readiness ─────────────────────────────────────────────────────


def api_health_check() -> dict[str, Any]:
    """Return the server health payload, or raise on failure."""
    url = f"{_http_base_url()}/health"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise EvalError(
            f"API server not reachable at {_http_base_url()}: {exc}"
        ) from exc


def wait_for_api_ready(
    timeout_seconds: float = 120.0,
    poll_interval: float = 1.0,
) -> None:
    """Block until the API server responds with a healthy status."""
    deadline = time.time() + timeout_seconds
    last_error: str | None = None
    while time.time() < deadline:
        try:
            api_health_check()
            return
        except Exception as exc:
            last_error = str(exc)
            time.sleep(poll_interval)
    raise EvalError(
        f"API server not ready after {timeout_seconds}s: {last_error}"
    )


# ── WebSocket RPC helpers ──────────────────────────────────────────────────


async def _rpc_request(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    *,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Send one RPC request over the events WebSocket and return the response.

    Connects to ``/api/v1/events``, sends an ``rpc`` message, waits for
    the matching ``rpc_response``, then closes the connection.
    """
    timeout = timeout or _eval_timeout()
    corr_id = uuid.uuid4().hex
    url = f"{_ws_base_url()}/api/v1/events"
    async with websockets.connect(url) as ws:
        await ws.send(
            json.dumps(
                {
                    "type": "rpc",
                    "id": corr_id,
                    "method": method.upper(),
                    "path": path,
                    "body": body or {},
                }
            )
        )
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                raw = await asyncio.wait_for(
                    ws.recv(), timeout=min(10, deadline - time.time())
                )
            except asyncio.TimeoutError:
                continue
            msg: dict = json.loads(raw)
            if msg.get("type") == "rpc_response" and msg.get("id") == corr_id:
                return msg
        raise TimeoutError(f"RPC {method} {path} timed out after {timeout}s")


def rpc_request_sync(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    *,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Synchronous wrapper around ``_rpc_request``."""
    return asyncio.run(_rpc_request(method, path, body, timeout=timeout))


# ── Knowledge-base document helpers ────────────────────────────────────────


def list_kb_documents() -> list[dict[str, Any]]:
    """Return all knowledge-base documents from the API."""
    resp = rpc_request_sync("GET", "/api/v1/knowledge-base/documents")
    if resp.get("status") != 200:
        raise RuntimeError(f"Failed to list KB documents: {resp}")
    body = resp.get("body", {})
    return list(body.get("documents", []))


def toggle_document_active(doc_id: int) -> dict[str, Any]:
    """Toggle a document's active state via the API."""
    resp = rpc_request_sync(
        "PATCH",
        f"/api/v1/knowledge-base/documents/{doc_id}/toggle-active",
    )
    if resp.get("status") != 200:
        raise RuntimeError(f"Failed to toggle document {doc_id}: {resp}")
    return resp.get("body", {})


def index_all_documents(force: bool = False) -> None:
    """Trigger indexing of all knowledge-base documents."""
    resp = rpc_request_sync(
        "POST",
        "/api/v1/knowledge-base/documents/index-all",
        {"force": force},
    )
    if resp.get("status") != 200:
        raise RuntimeError(f"Failed to index all documents: {resp}")


def cancel_indexing() -> None:
    """Cancel in-progress indexing."""
    rpc_request_sync(
        "POST",
        "/api/v1/knowledge-base/documents/index-cancel",
    )


def wait_for_document_indexed(
    doc_id: int,
    *,
    timeout_seconds: float = 300.0,
    poll_interval: float = 1.0,
) -> None:
    """Block until a document's ``indexed`` flag is True."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        docs = list_kb_documents()
        for doc in docs:
            if doc.get("id") == doc_id and doc.get("indexed"):
                return
        time.sleep(poll_interval)
    raise EvalError(f"Document {doc_id} not indexed after {timeout_seconds}s")


def ensure_document_active(doc_id: int) -> None:
    """Make sure one document is in the *active* state."""
    docs = list_kb_documents()
    for doc in docs:
        if doc.get("id") == doc_id:
            if doc.get("active"):
                return
            toggle_document_active(doc_id)
            return
    raise RuntimeError(f"Document {doc_id} not found in KB")


def find_document_by_path(doc_path: str) -> dict[str, Any] | None:
    """Return the first KB document whose path matches, or None."""
    docs = list_kb_documents()
    for doc in docs:
        if str(doc.get("path", "")).endswith(doc_path):
            return doc
    return None


# ── Conversation helpers ───────────────────────────────────────────────────


def create_conversation() -> int:
    """Create a new conversation via the API and return its ID."""
    resp = rpc_request_sync("POST", "/api/v1/llm/conversations")
    if resp.get("status") != 200:
        raise RuntimeError(f"Failed to create conversation: {resp}")
    body = resp.get("body", {})
    conv_id = body.get("id") or body.get("conversation_id")
    if not conv_id:
        raise RuntimeError(f"No conversation ID in response: {resp}")
    return int(conv_id)


def delete_conversation(conv_id: int) -> None:
    """Delete one conversation."""
    rpc_request_sync(
        "DELETE",
        f"/api/v1/llm/conversations/{conv_id}",
    )


# ── LLM chat via WebSocket ─────────────────────────────────────────────────


async def _llm_chat(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 128,
    active_document_ids: list[int] | None = None,
    conversation_id: int | None = None,
    timeout: float | None = None,
) -> StreamCollector:
    """Send a chat request over ``/api/v1/llm/stream`` and collect the response.

    Returns a ``StreamCollector`` with the assembled text and tool calls.
    """
    timeout = timeout or _eval_timeout()
    url = f"{_ws_base_url()}/api/v1/llm/stream"
    collector = StreamCollector()

    payload: dict[str, Any] = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }
    if model:
        payload["model"] = model
    if active_document_ids:
        payload["active_document_ids"] = active_document_ids
    if conversation_id:
        payload["conversation_id"] = conversation_id

    async with websockets.connect(url) as ws:
        await ws.send(json.dumps(payload))
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                raw = await asyncio.wait_for(
                    ws.recv(), timeout=min(10, deadline - time.time())
                )
            except asyncio.TimeoutError:
                continue
            msg: dict = json.loads(raw)
            msg_type = msg.get("type", "")

            if msg_type == "chunk":
                collector.append_chunk(str(msg.get("content", "")))
                tool = msg.get("tool_calls")
                if tool:
                    collector.add_tool_calls(
                        tool if isinstance(tool, list) else [tool]
                    )
                if msg.get("done"):
                    collector.final = True
                    collector.full_message = collector.text or str(
                        msg.get("content", "")
                    )
                    return collector
            elif msg_type == "thinking":
                collector.append_thinking(str(msg.get("content", "")))
            elif msg_type == "tool_status":
                collector.add_tool_calls([msg])
            elif msg_type == "error":
                collector.error = str(msg.get("content", ""))
                collector.final = True
                return collector

        raise TimeoutError(f"LLM chat timed out after {timeout}s")


def llm_chat_sync(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 128,
    active_document_ids: list[int] | None = None,
    conversation_id: int | None = None,
    timeout: float | None = None,
) -> StreamCollector:
    """Synchronous wrapper around ``_llm_chat``."""
    return asyncio.run(
        _llm_chat(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            active_document_ids=active_document_ids,
            conversation_id=conversation_id,
            timeout=timeout,
        )
    )


# ── Visible message helpers ────────────────────────────────────────────────


def visible_llm_message(message: str) -> str:
    """Return an assistant-visible reply without status or thinking text."""
    without_thinking = _re.sub(
        r"<think>.*?</think>",
        "",
        message,
        flags=_re.DOTALL | _re.IGNORECASE,
    )
    lines: list[str] = []
    for raw_line in without_thinking.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("\U0001f527") or line.startswith("\u2705"):
            continue
        lines.append(line)
    return " ".join(lines).strip()


def visible_digits(message: str) -> str:
    """Return only the visible numeric portion of one LLM response."""
    return _re.sub(r"[^0-9]", "", visible_llm_message(message))


def visible_last_number(message: str) -> str:
    """Return the last visible number-like token from one LLM response."""
    matches = _re.findall(r"\d(?:[\s.,_-]*\d)*", visible_llm_message(message))
    if not matches:
        return ""
    return _re.sub(r"[^0-9]", "", matches[-1])


# ── Assertion helpers ──────────────────────────────────────────────────────


def assert_success(collector: StreamCollector) -> None:
    """Assert that one LLM chat completed successfully."""
    if collector.error:
        raise EvalError(f"LLM chat error: {collector.error}")
    assert (
        collector.final
    ), f"Chat did not complete. Chunks: {collector.chunks[-3:]}"
    assert collector.text or collector.full_message, "Empty response from LLM"


def assert_tool_names(
    collector: StreamCollector,
    *,
    expected: set[str],
) -> None:
    """Assert the executed tool names exactly match the expected set."""
    observed = set(collector.tool_names)
    assert observed == expected, (
        f"Expected tools {expected}, got {observed}. "
        f"Full text: {collector.text[:200]}"
    )


# ── RAG-specific assertion helpers ─────────────────────────────────────────


def assert_rag_context_injected(
    collector: StreamCollector,
) -> None:
    """Assert that the LLM response references RAG document content."""
    text = collector.text.lower()
    assert text, "Empty response — cannot check for RAG content"


def _resolve_doc_path(file_path: str | Path) -> str:
    """Resolve a fixture path to an absolute path usable in assertions."""
    return str(Path(file_path).resolve())


# ── Model resolution ───────────────────────────────────────────────────────


def resolve_active_model() -> str:
    """Return the model ID to use for eval tests.

    Reads ``AIRUNNER_EVAL_MODEL`` env var, falling back to ``qwen3.5-9b``.
    """
    return os.environ.get("AIRUNNER_EVAL_MODEL", "qwen3.5-9b")


def resolve_system_bot_chatbot_id() -> int | None:
    """Return the system-bot chatbot ID, or None if not configured.

    Reads ``AIRUNNER_SYSTEM_BOT_CHATBOT_ID``.  When set, the test can
    target the real system bot (``is_system_bot=True``) through the
    production prompt stack including ``BANNED_PATTERNS_BLOCK`` and
    ``uwu_system_bot_style()``.
    """
    raw = os.environ.get("AIRUNNER_SYSTEM_BOT_CHATBOT_ID", "")
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


# ── Pre-test fixture for API readiness ─────────────────────────────────────


# Fixture is in conftest.py — do NOT import pytest at module level here.


__all__ = [
    "EvalResult",
    "StreamCollector",
    "api_health_check",
    "assert_rag_context_injected",
    "assert_success",
    "assert_tool_names",
    "cancel_indexing",
    "create_conversation",
    "delete_conversation",
    "ensure_document_active",
    "find_document_by_path",
    "index_all_documents",
    "list_kb_documents",
    "llm_chat_sync",
    "resolve_active_model",
    "resolve_system_bot_chatbot_id",
    "rpc_request_sync",
    "toggle_document_active",
    "visible_digits",
    "visible_last_number",
    "visible_llm_message",
    "wait_for_api_ready",
    "wait_for_document_indexed",
]
