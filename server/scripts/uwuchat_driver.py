#!/usr/bin/env python3
"""Drive UwUChat over its real client protocol, without a browser.

Speaks exactly what the React client speaks: HTTP login, the shared
WebSocket-RPC channel (``/api/v1/events``) for CRUD calls, and the
dedicated LLM streaming channel (``/api/v1/llm/stream``) for chat. See
wiki/WebSocket-RPC.md for the protocol this mirrors.

Run inside the server container (it needs the app's own network
reachability and, for some commands, DB access is irrelevant — it only
talks HTTP/WS to itself):

    docker compose exec server python server/scripts/uwuchat_driver.py \\
        --help

Examples:

    # Sanity check: log in and list chatbots.
    docker compose exec server python server/scripts/uwuchat_driver.py \\
        chatbots

    # Send one chat message and print the streamed reply.
    docker compose exec server python server/scripts/uwuchat_driver.py \\
        chat --chatbot-id 1 --message "hello"

    # Toggle code mode on a conversation.
    docker compose exec server python server/scripts/uwuchat_driver.py \\
        code-mode-set --conversation-id 3 --enabled true
"""

from __future__ import annotations

import argparse
import asyncio
import itertools
import json
import sys
from typing import Any

import requests
import websockets

DEFAULT_BASE_URL = "http://localhost:8080"
DEFAULT_WS_BASE = "ws://localhost:8080"


class UwuChatError(RuntimeError):
    """Raised for any non-2xx/failed operation against the app."""


class UwuChatClient:
    """A minimal client speaking the exact protocol the React app does."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        ws_base: str = DEFAULT_WS_BASE,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.ws_base = ws_base.rstrip("/")
        self.access_token: str | None = None
        self._rpc_id_counter = itertools.count(1)

    # ── Auth ──────────────────────────────────────────────────────

    def login(self, email: str, password: str) -> None:
        resp = requests.post(
            f"{self.base_url}/api/v1/auth/login",
            json={"email": email, "password": password},
            timeout=15,
        )
        if resp.status_code != 200:
            raise UwuChatError(
                f"login failed: {resp.status_code} {resp.text[:200]}"
            )
        self.access_token = resp.json()["access_token"]

    def _require_token(self) -> str:
        if not self.access_token:
            raise UwuChatError("call login() first")
        return self.access_token

    # ── Generic RPC channel (/api/v1/events) ────────────────────────

    async def rpc(
        self, method: str, path: str, body: dict[str, Any] | None = None,
        timeout: float = 20.0,
    ) -> dict[str, Any]:
        """Send one RPC call and return its ``{status, body}`` result."""
        token = self._require_token()
        rpc_id = str(next(self._rpc_id_counter))
        url = f"{self.ws_base}/api/v1/events?token={token}"
        async with websockets.connect(url, open_timeout=15) as ws:
            await ws.send(json.dumps(
                {
                    "type": "rpc",
                    "id": rpc_id,
                    "method": method.upper(),
                    "path": path,
                    "body": body or {},
                }
            ))
            async with asyncio.timeout(timeout):
                while True:
                    raw = await ws.recv()
                    msg = json.loads(raw)
                    if (
                        msg.get("type") == "rpc_response"
                        and msg.get("id") == rpc_id
                    ):
                        return msg

    def rpc_sync(
        self, method: str, path: str, body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return asyncio.run(self.rpc(method, path, body))

    # ── Chat streaming channel (/api/v1/llm/stream) ─────────────────

    async def chat(
        self,
        message: str,
        chatbot_id: int,
        conversation_id: int | None = None,
        timeout: float = 120.0,
    ) -> dict[str, Any]:
        """Send one chat message; return the assembled reply + raw frames.

        Returns ``{"content": str, "frames": list[dict], "conversation_id": ...}``.
        """
        token = self._require_token()
        url = f"{self.ws_base}/api/v1/llm/stream?token={token}"
        frames: list[dict[str, Any]] = []
        content_parts: list[str] = []
        seen_conversation_id = conversation_id
        async with websockets.connect(url, open_timeout=15) as ws:
            payload: dict[str, Any] = {
                "type": "chat",
                "messages": [{"role": "user", "content": message}],
                "chatbot_id": chatbot_id,
            }
            if conversation_id is not None:
                payload["conversation_id"] = conversation_id
            await ws.send(json.dumps(payload))
            async with asyncio.timeout(timeout):
                while True:
                    raw = await ws.recv()
                    msg = json.loads(raw)
                    frames.append(msg)
                    if msg.get("conversation_id"):
                        seen_conversation_id = msg["conversation_id"]
                    piece = msg.get("content")
                    if msg.get("type") == "chunk" and isinstance(piece, str):
                        content_parts.append(piece)
                    if msg.get("done"):
                        break
        return {
            "content": "".join(content_parts),
            "frames": frames,
            "conversation_id": seen_conversation_id,
        }

    def chat_sync(
        self,
        message: str,
        chatbot_id: int,
        conversation_id: int | None = None,
        timeout: float = 120.0,
    ) -> dict[str, Any]:
        return asyncio.run(
            self.chat(message, chatbot_id, conversation_id, timeout)
        )

    # ── Bootstrap (pushed automatically on /api/v1/events connect) ──

    async def bootstrap(self, timeout: float = 15.0) -> dict[str, Any]:
        """Connect, read the auto-pushed ``bootstrap`` frame, disconnect.

        This is where the chatbot roster, app settings, and language
        settings come from — there is no dedicated "list chatbots" RPC
        (see events_bootstrap.py's ``build_bootstrap_payload``).
        """
        token = self._require_token()
        url = f"{self.ws_base}/api/v1/events?token={token}"
        async with websockets.connect(url, open_timeout=15) as ws:
            async with asyncio.timeout(timeout):
                while True:
                    raw = await ws.recv()
                    msg = json.loads(raw)
                    if msg.get("type") == "bootstrap":
                        return msg.get("body", {})

    def bootstrap_sync(self, timeout: float = 15.0) -> dict[str, Any]:
        return asyncio.run(self.bootstrap(timeout))

    # ── Convenience wrappers over common RPCs ────────────────────────

    def list_chatbots(self) -> Any:
        return self.bootstrap_sync().get("chatbots", [])

    def code_mode_get(self, conversation_id: int) -> Any:
        return self.rpc_sync(
            "GET", f"/api/v1/uwuchat/code-mode/{conversation_id}",
        )

    def code_mode_set(self, conversation_id: int, enabled: bool) -> Any:
        return self.rpc_sync(
            "PUT",
            f"/api/v1/uwuchat/code-mode/{conversation_id}",
            {"enabled": enabled},
        )


def _print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _build_client(args: argparse.Namespace) -> UwuChatClient:
    client = UwuChatClient(base_url=args.base_url, ws_base=args.ws_base)
    client.login(args.email, args.password)
    return client


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--ws-base", default=DEFAULT_WS_BASE)
    parser.add_argument("--email", default="admin@example.com")
    parser.add_argument("--password", default="admin123")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("chatbots", help="List chatbots for the account")
    sub.add_parser("bootstrap", help="Print the raw bootstrap payload")

    p_chat = sub.add_parser("chat", help="Send one chat message")
    p_chat.add_argument("--chatbot-id", type=int, required=True)
    p_chat.add_argument("--conversation-id", type=int, default=None)
    p_chat.add_argument("--message", required=True)
    p_chat.add_argument("--timeout", type=float, default=120.0)

    p_get = sub.add_parser("code-mode-get")
    p_get.add_argument("--conversation-id", type=int, required=True)

    p_set = sub.add_parser("code-mode-set")
    p_set.add_argument("--conversation-id", type=int, required=True)
    p_set.add_argument(
        "--enabled", choices=["true", "false"], required=True,
    )

    p_rpc = sub.add_parser("rpc", help="Send an arbitrary RPC call")
    p_rpc.add_argument("--method", required=True)
    p_rpc.add_argument("--path", required=True)
    p_rpc.add_argument(
        "--body", default="{}", help="JSON-encoded request body",
    )

    args = parser.parse_args()
    client = _build_client(args)

    if args.command == "chatbots":
        _print_json(client.list_chatbots())
    elif args.command == "bootstrap":
        _print_json(client.bootstrap_sync())
    elif args.command == "chat":
        _print_json(
            client.chat_sync(
                args.message,
                args.chatbot_id,
                args.conversation_id,
                args.timeout,
            )
        )
    elif args.command == "code-mode-get":
        _print_json(client.code_mode_get(args.conversation_id))
    elif args.command == "code-mode-set":
        _print_json(
            client.code_mode_set(
                args.conversation_id, args.enabled == "true",
            )
        )
    elif args.command == "rpc":
        _print_json(
            client.rpc_sync(args.method, args.path, json.loads(args.body))
        )
    else:  # pragma: no cover - argparse enforces valid choices
        parser.error(f"unknown command {args.command!r}")
        sys.exit(2)


if __name__ == "__main__":
    main()
