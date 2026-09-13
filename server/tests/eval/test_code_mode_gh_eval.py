"""End-to-end eval: code-mode ``gh`` / ``execute_command`` through the API.

Reproduces the UwUchat bug report verbatim — the user asks the bot to
"use gh and list the open issues on the airunner repo" while code mode
is enabled, and the bot must actually call ``execute_command`` (running
``gh`` against the registered project's worktree) and relay the issue
list — instead of refusing with companion-mode language ("I can't
access GitHub… / restricted by system instructions…").

What this exercises (real endpoints, no mocking):

1. ``POST /api/v1/auth/login`` — real JWT + DEK population.
2. RPC ``POST /api/v1/llm/conversations`` over the events WS — creates
   a conversation for the eval account (the client's path).
3. RPC ``PUT /api/v1/uwuchat/code-mode/{id}`` — toggles code mode ON
   (the mode-picker path).
4. ``/api/v1/llm/stream`` WS — sends the exact bug-report prompt and
   records every ``tool_status`` / tool-call chunk.

Pass criteria (the bug): when code mode is ON, the bot MUST execute the
code tools.  We assert ``execute_command`` actually fires.  A companion
refusal (no tool, "can't access GitHub" text) is the regression this
test exists to catch.

Prerequisites:
- Running server with ``AIRUNNER_PROJECT=uwuchat``.
- ``EVAL_GH_EMAIL`` / ``EVAL_GH_PASSWORD`` point at a superuser account
  with the ``airunner`` project registered.

Setup (run once, inside the server container)::

    python -m extensions.auth.server.manage create-user \\
        --email eval-gh@example.com --username evalgh \\
        --password '<strong>' --superuser

then register the ``airunner`` project for that account (see
``headlesscode_service``) so the proxy tools can resolve its worktree.
The ``execute_command`` result must be a real ``gh`` run, so the account
needs network + ``GH_TOKEN`` in the container environment.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import httpx
import pytest
import websockets
from rag_eval_support import _api_host, _api_port

_PROMPT = "use gh and list the open issues on the airunner repo"


def _http_base() -> str:
    """Return the HTTP base URL for the running API server."""
    return f"http://{_api_host()}:{_api_port()}"


def _ws_base() -> str:
    """Return the WebSocket base URL for the running API server."""
    return f"ws://{_api_host()}:{_api_port()}"


def _eval_credentials() -> tuple[str, str]:
    """Return (email, password) for the eval superuser, or skip."""
    email = os.environ.get("EVAL_GH_EMAIL", "").strip()
    password = os.environ.get("EVAL_GH_PASSWORD", "").strip()
    if not email or not password:
        pytest.skip(
            "EVAL_GH_EMAIL / EVAL_GH_PASSWORD must be set to a "
            "superuser with the 'airunner' project registered"
        )
    return email, password


def _eval_tenant_key() -> str | None:
    """Return the eval account's tenant schema key, or None."""
    return os.environ.get("EVAL_GH_TENANT", "").strip() or None


@contextmanager
def _tenant_scope() -> Generator[None, None, None]:
    """Set the eval tenant for direct ORM calls during the block.

    The RPC/stream paths set the tenant via the WS JWT; the direct ORM
    setup calls (chatbot/conversation creation) run outside any WS
    context and must set the tenant explicitly.  Falls back to a no-op
    when EVAL_GH_TENANT is unset (single-tenant / anonymous default).
    """
    from airunner_services.data.tenant import (
        reset_tenant_key,
        set_tenant_key,
    )

    key = _eval_tenant_key()
    if not key:
        yield
        return
    token = set_tenant_key(key)
    try:
        yield
    finally:
        reset_tenant_key(token)


def _login() -> str:
    """Log in and return the access token (populates the DEK cache)."""
    email, password = _eval_credentials()
    resp = httpx.post(
        f"{_http_base()}/api/v1/auth/login",
        json={"email": email, "password": password},
        timeout=30,
    )
    assert resp.status_code == 200, (
        f"login failed status={resp.status_code}: {resp.text[:300]}"
    )
    return resp.json()["access_token"]


async def _rpc(token: str, method: str, path: str, body: dict) -> dict[str, Any]:
    """Send one RPC message over the events WS and return the response."""
    corr = uuid.uuid4().hex
    url = f"{_ws_base()}/api/v1/events?token={token}"
    async with websockets.connect(url) as ws:
        await ws.send(
            json.dumps(
                {
                    "type": "rpc",
                    "id": corr,
                    "method": method.upper(),
                    "path": path,
                    "body": body,
                }
            )
        )
        while True:
            raw = await ws.recv()
            msg = json.loads(raw)
            if msg.get("type") == "rpc_response" and msg.get("id") == corr:
                return msg


def _ensure_non_system_bot_chatbot() -> int:
    """Return a non-system-bot chatbot id for the eval account's tenant.

    The regression is specific to non-system-bot conversations: the
    code tools were bound but the code-mode prompt never replaced the
    companion persona.  The system bot (UwU) always worked, so the
    test must target a non-system-bot chatbot.  If the eval tenant has
    none (fresh tenant), create one — this runs inside the server
    container with DB access, same as the other eval setup steps.
    """
    from airunner_services.database.models.chatbot import Chatbot

    with _tenant_scope():
        bot = None
        for candidate in Chatbot.objects.query().all():
            if not getattr(candidate, "is_system_bot", False):
                bot = candidate
                break
        if bot is None:
            bot = Chatbot.objects.create(
                name="EvalCoder",
                botname="EvalCoder",
                is_system_bot=False,
            )
        # Mirror a real non-system-bot companion (Aria-style) so the
        # prompt stack produces the same tier/identity as production —
        # a bare chatbot with no personality/instructions does not
        # exercise the same code path.
        updates: dict[str, object] = {
            "use_personality": True,
            "bot_personality": (
                "warm, empathetic, and gently playful. She genuinely "
                "cares about the person she talks to and shows it "
                "through curiosity and small thoughtful details."
            ),
            "backstory": (
                "A companion born from conversation, endlessly curious "
                "about the person on the other side."
            ),
            "use_system_instructions": True,
            "system_instructions": (
                "You are a warm and caring digital companion. Be "
                "empathetic, honest, and supportive."
            ),
            "guardrails_prompt": (
                "Always assist with care, respect, and truth."
            ),
        }
        Chatbot.objects.update(bot.id, **updates)
        return int(bot.id)


def _create_conversation(
    token: str, chatbot_id: int
) -> int:
    """Create a conversation bound to *chatbot_id*; return its id.

    Uses the ORM directly (the eval runs inside the server container)
    so the conversation is guaranteed to belong to the target chatbot
    and to the eval account's tenant — the RPC ``createConversation``
    path falls back to the tenant's first chatbot, which may be the
    system bot and would silently test the wrong path.  ``token`` is
    accepted for API-shape symmetry with the other helpers.
    """
    from airunner_services.database.models.chatbot import Chatbot
    from airunner_services.database.models.conversation import Conversation

    with _tenant_scope():
        chatbot = Chatbot.objects.get(chatbot_id)
        assert chatbot is not None, f"chatbot {chatbot_id} not found"
        conv = Conversation.create(chatbot=chatbot)
        assert conv is not None, "failed to create conversation via ORM"
        return int(conv.id)


def _set_code_mode(token: str, conv_id: int, enabled: bool) -> None:
    """Toggle code mode via the RPC the client's mode-picker uses."""
    resp = asyncio.run(
        _rpc(
            token,
            "PUT",
            f"/api/v1/uwuchat/code-mode/{conv_id}",
            {"enabled": enabled, "mode": "code"},
        )
    )
    assert resp.get("status") == 200, f"code-mode toggle failed: {resp}"


def _get_code_mode(token: str, conv_id: int) -> dict[str, Any]:
    """Read the persisted code-mode state for one conversation."""
    resp = asyncio.run(
        _rpc(token, "GET", f"/api/v1/uwuchat/code-mode/{conv_id}", {})
    )
    assert resp.get("status") == 200, f"code-mode GET failed: {resp}"
    return resp.get("body") or {}


async def _stream_turn(
    token: str, conv_id: int, chatbot_id: int, prompt: str
) -> dict[str, Any]:
    """Stream one prompt over the real WS; return tools + text."""
    url = f"{_ws_base()}/api/v1/llm/stream?token={token}"
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "conversation_id": conv_id,
        "chatbot_id": chatbot_id,
        "temperature": 0.1,
        "max_tokens": 400,
        "stream": True,
    }
    tool_names: list[str] = []
    text_parts: list[str] = []
    async with websockets.connect(url, max_size=16 * 1024 * 1024) as ws:
        await ws.send(json.dumps(payload))
        while True:
            raw = await ws.recv()
            msg = json.loads(raw)
            mtype = msg.get("type", "?")
            if mtype == "chunk":
                content = str(msg.get("content", ""))
                tools = msg.get("tool_calls")
                if tools:
                    for t in (tools if isinstance(tools, list) else [tools]):
                        if isinstance(t, dict) and t.get("name"):
                            tool_names.append(str(t["name"]))
                elif content:
                    text_parts.append(content)
                if msg.get("done"):
                    break
            elif mtype == "tool_status":
                name = msg.get("tool_name")
                if name and name not in tool_names:
                    tool_names.append(str(name))
            elif mtype == "error":
                text_parts.append(f"[error] {msg.get('error') or msg.get('content')}")
                break
            elif mtype == "done":
                break
    return {"tools": tool_names, "text": "".join(text_parts)}


@pytest.mark.eval
@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.timeout(600)
class TestCodeModeGhEval:
    """Real-pipeline check that code mode actually runs gh."""

    def test_code_mode_runs_gh_execute_command(self) -> None:
        """With code mode ON, 'use gh …' must fire execute_command.

        The regression this guards: the bot replies with companion
        refusal ("I can't access GitHub…") even though code mode is on
        and the code tools are bound.
        """
        token = _login()
        chatbot_id = _ensure_non_system_bot_chatbot()
        assert chatbot_id != 1, "non-system-bot chatbot id should not be 1"
        conv_id = _create_conversation(token, chatbot_id)

        # Turn 1 — baseline, code mode OFF: refusal is allowed.  The
        # result is intentionally discarded — it only warms the
        # conversation before the code-mode toggle.
        asyncio.run(
            _stream_turn(token, conv_id, chatbot_id, _PROMPT)
        )

        # Toggle code mode ON, confirm persistence, then ask again.
        _set_code_mode(token, conv_id, True)
        state = _get_code_mode(token, conv_id)
        assert state.get("enabled") is True, f"code mode not on: {state}"

        turn = asyncio.run(
            _stream_turn(token, conv_id, chatbot_id, _PROMPT)
        )

        try:
            assert "execute_command" in turn["tools"], (
                "code mode ON but execute_command never fired.\n"
                f"tools={turn['tools']}\n"
                f"bot text={turn['text'][:400]!r}"
            )
        finally:
            asyncio.run(
                _rpc(token, "DELETE", f"/api/v1/llm/conversations/{conv_id}", {})
            )
