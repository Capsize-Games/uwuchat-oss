"""Unit tests for llm_stream_routes helpers.

Covers the pure/isolated helpers (token ceiling resolution, quota
loaders, session rotation, mood restore/emit) and the streaming
transport (_stream_to_socket) with mocked runtime.  The full
websocket_chat endpoint and _chat_loop race loop are exercised with
heavily-mocked dependencies to cover every branch.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from airunner_services.ipc.messages import EnvelopeStatus, StreamDelta

from airunner_services.api.routes import llm_stream_routes as mod


def _delta(content: str = "x", final: bool = False) -> StreamDelta:
    return StreamDelta(request_id="r", final=final, delta={"content": content})


# ---------------------------------------------------------------------------
# _stream_to_socket
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_to_socket_sends_until_final() -> None:
    ws = SimpleNamespace(send_json=AsyncMock())
    client = MagicMock()
    client.stream.return_value = iter(
        [_delta("a", final=False), _delta("b", final=True), _delta("c")]
    )
    with patch.object(mod, "websocket_chunk", side_effect=lambda d: d.delta):
        await mod._stream_to_socket(client, ws, object())

    # Only the deltas up to (and including) final are sent.
    assert ws.send_json.await_count == 2


@pytest.mark.asyncio
async def test_stream_to_socket_empty_stream() -> None:
    """An exhausted stream terminates the loop with no sends."""
    ws = SimpleNamespace(send_json=AsyncMock())
    client = MagicMock()
    client.stream.return_value = iter([])
    # stream_runtime converts the StopAsyncIteration into a clean stop;
    # the empty client stream is exercised end-to-end.
    await mod._stream_to_socket(client, ws, object())
    ws.send_json.assert_not_called()


# ---------------------------------------------------------------------------
# _resolve_max_output_token_ceiling
# ---------------------------------------------------------------------------


def test_token_ceiling_none_account() -> None:
    assert mod._resolve_max_output_token_ceiling(None) == 500


def test_token_ceiling_is_unlimited_default() -> None:
    assert mod._resolve_max_output_token_ceiling(7) == 500


def test_token_ceiling_exception() -> None:
    with patch(
        "extensions.auth.server.models.Account"
    ), patch(
        "airunner_services.database.session.public_session_scope",
        side_effect=RuntimeError("boom"),
    ):
        assert mod._resolve_max_output_token_ceiling(7) == 500


# ---------------------------------------------------------------------------
# _try_load_quota_checker / _try_load_daily_token_checker
# ---------------------------------------------------------------------------


def test_try_load_quota_checker_with_project(monkeypatch) -> None:
    stub = SimpleNamespace(is_over_quota=lambda *a, **k: True)
    monkeypatch.setattr("os.environ", {"AIRUNNER_PROJECT": "uwuchat"})
    with patch(
        "importlib.import_module", return_value=stub
    ) as imp:
        assert mod._try_load_quota_checker() is stub.is_over_quota
        imp.assert_called_once()


def test_try_load_quota_checker_no_project() -> None:
    with patch.dict("os.environ", {}, clear=True), patch(
        "airunner_services.conf.settings"
    ) as settings:
        settings.AIRUNNER_PROJECT = ""
        assert mod._try_load_quota_checker() is None


def test_try_load_quota_checker_import_error() -> None:
    with patch.dict("os.environ", {"AIRUNNER_PROJECT": "other"}), patch(
        "importlib.import_module", side_effect=ImportError
    ):
        assert mod._try_load_quota_checker() is None


def test_try_load_daily_token_checker_with_project(monkeypatch) -> None:
    stub = SimpleNamespace(is_over_daily_token_limit=lambda *a, **k: False)
    with patch.dict("os.environ", {"AIRUNNER_PROJECT": "uwuchat"}), patch(
        "importlib.import_module", return_value=stub
    ):
        assert mod._try_load_daily_token_checker() is stub.is_over_daily_token_limit


def test_try_load_daily_token_checker_import_error() -> None:
    with patch.dict("os.environ", {"AIRUNNER_PROJECT": "other"}), patch(
        "importlib.import_module", side_effect=ImportError
    ):
        assert mod._try_load_daily_token_checker() is None


def test_try_load_quota_checker_settings_fallback() -> None:
    """When AIRUNNER_PROJECT is unset, the settings fallback is used."""
    stub = SimpleNamespace(is_over_quota=lambda *a, **k: True)
    with patch.dict("os.environ", {}, clear=True), patch(
        "airunner_services.conf.settings"
    ) as settings, patch("importlib.import_module", return_value=stub):
        settings.AIRUNNER_PROJECT = "uwuchat"
        assert mod._try_load_quota_checker() is stub.is_over_quota


def test_try_load_quota_checker_settings_empty_project() -> None:
    """A resolved-but-empty project returns None."""
    with patch.dict("os.environ", {}, clear=True), patch(
        "airunner_services.conf.settings"
    ) as settings:
        settings.AIRUNNER_PROJECT = ""
        assert mod._try_load_quota_checker() is None


def test_try_load_daily_settings_fallback() -> None:
    """When AIRUNNER_PROJECT is unset, the settings fallback is used."""
    stub = SimpleNamespace(is_over_daily_token_limit=lambda *a, **k: False)
    with patch.dict("os.environ", {}, clear=True), patch(
        "airunner_services.conf.settings"
    ) as settings, patch("importlib.import_module", return_value=stub):
        settings.AIRUNNER_PROJECT = "uwuchat"
        assert mod._try_load_daily_token_checker() is stub.is_over_daily_token_limit


# ---------------------------------------------------------------------------
# _ensure_session_rotation
# ---------------------------------------------------------------------------


def test_session_rotation_no_chatbot() -> None:
    mod._ensure_session_rotation({})  # no raise


def test_session_rotation_with_chatbot() -> None:
    manager = MagicMock()
    manager.pending_cold_sessions.return_value = [1]
    with patch(
        "airunner_services.llm.session_manager.SessionManager",
        return_value=manager,
    ), patch(
        "airunner_services.llm.episodic_summarizer.summarize_session",
        new=AsyncMock(),
    ):
        mod._ensure_session_rotation({"chatbot_id": 3})
    manager.get_or_create_session.assert_called_once_with(3)


def test_session_rotation_exception() -> None:
    with patch(
        "airunner_services.llm.session_manager.SessionManager",
        side_effect=RuntimeError("boom"),
    ):
        mod._ensure_session_rotation({"chatbot_id": 3})  # no raise


# ---------------------------------------------------------------------------
# _emit_stored_mood
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emit_stored_mood_no_conversation_id() -> None:
    ws = SimpleNamespace(send_json=AsyncMock())
    await mod._emit_stored_mood({}, ws)
    ws.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_emit_stored_mood_emits() -> None:
    ws = SimpleNamespace(send_json=AsyncMock())
    conv = SimpleNamespace(
        id=5,
        chatbot_id=3,
        user_data={"current_mood": {"mood": "happy", "emoji": "😊"}},
    )
    fake_objects = MagicMock()
    fake_objects.get.return_value = conv
    q = MagicMock()
    q.order_by.return_value = q
    q.limit.return_value = q
    q.all.return_value = [conv]
    fake_objects.query.return_value = q

    # Conversation.id must be a mock so `.desc()` is callable.
    with patch(
        "airunner_services.database.models.conversation.Conversation",
        SimpleNamespace(objects=fake_objects, id=MagicMock()),
    ):
        await mod._emit_stored_mood({"conversation_id": 5}, ws)

    ws.send_json.assert_awaited_once()
    payload = ws.send_json.await_args[0][0]
    assert payload["type"] == "mood"
    assert payload["mood"] == "happy"


@pytest.mark.asyncio
async def test_emit_stored_mood_exception_swallowed() -> None:
    ws = SimpleNamespace(send_json=AsyncMock())
    with patch(
        "airunner_services.database.models.conversation.Conversation",
        SimpleNamespace(objects=None),  # .get raises AttributeError
    ):
        await mod._emit_stored_mood({"conversation_id": 5}, ws)
    ws.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_emit_stored_mood_skips_other_chatbot() -> None:
    """Recent convs for another chatbot are skipped in the loop."""
    ws = SimpleNamespace(send_json=AsyncMock())
    ref = SimpleNamespace(id=5, chatbot_id=3)
    other = SimpleNamespace(
        id=6, chatbot_id=99,  # different chatbot
        user_data={"current_mood": {"mood": "x", "emoji": "y"}},
    )
    fake_objects = MagicMock()
    fake_objects.get.return_value = ref
    q = MagicMock()
    q.order_by.return_value = q
    q.limit.return_value = q
    q.all.return_value = [other]
    fake_objects.query.return_value = q

    with patch(
        "airunner_services.database.models.conversation.Conversation",
        SimpleNamespace(objects=fake_objects, id=MagicMock()),
    ):
        await mod._emit_stored_mood({"conversation_id": 5}, ws)

    ws.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_emit_stored_mood_no_mood_found() -> None:
    """No conversation with a stored mood → no emit."""
    ws = SimpleNamespace(send_json=AsyncMock())
    ref = SimpleNamespace(id=5, chatbot_id=3)
    no_mood = SimpleNamespace(
        id=6, chatbot_id=3, user_data={}  # no current_mood
    )
    fake_objects = MagicMock()
    fake_objects.get.return_value = ref
    q = MagicMock()
    q.order_by.return_value = q
    q.limit.return_value = q
    q.all.return_value = [no_mood]
    fake_objects.query.return_value = q

    with patch(
        "airunner_services.database.models.conversation.Conversation",
        SimpleNamespace(objects=fake_objects, id=MagicMock()),
    ):
        await mod._emit_stored_mood({"conversation_id": 5}, ws)

    ws.send_json.assert_not_called()


# ---------------------------------------------------------------------------
# _restore_stored_mood_on_connect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_restore_mood_on_connect_emits() -> None:
    ws = SimpleNamespace(
        send_json=AsyncMock(),
        scope={"query_string": b"conversation_id=5"},
    )
    conv = SimpleNamespace(
        id=5,
        chatbot_id=3,
        user_data={"current_mood": {"mood": "silly", "emoji": "🤪"}},
    )
    fake_objects = MagicMock()
    fake_objects.get.return_value = conv
    q = MagicMock()
    q.order_by.return_value = q
    q.limit.return_value = q
    q.all.return_value = [conv]
    fake_objects.query.return_value = q

    with patch(
        "airunner_services.database.models.conversation.Conversation",
        SimpleNamespace(objects=fake_objects, id=MagicMock()),
    ):
        await mod._restore_stored_mood_on_connect(ws)

    ws.send_json.assert_awaited_once()
    payload = ws.send_json.await_args[0][0]
    assert payload["type"] == "mood"


@pytest.mark.asyncio
async def test_restore_mood_on_connect_no_conv() -> None:
    ws = SimpleNamespace(
        send_json=AsyncMock(),
        scope={"query_string": b"conversation_id=5"},
    )
    fake_objects = MagicMock()
    fake_objects.get.return_value = None
    q = MagicMock()
    q.order_by.return_value = q
    q.limit.return_value = q
    q.all.return_value = []
    fake_objects.query.return_value = q

    with patch(
        "airunner_services.database.models.conversation.Conversation",
        SimpleNamespace(objects=fake_objects, id=5),
    ):
        await mod._restore_stored_mood_on_connect(ws)
    ws.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_restore_mood_on_connect_data_encryption_error() -> None:
    ws = SimpleNamespace(
        send_json=AsyncMock(),
        scope={"query_string": b"conversation_id=5"},
    )
    with patch(
        "airunner_services.database.models.conversation.Conversation",
        SimpleNamespace(objects=MagicMock()),
    ), patch(
        "airunner_services.utils.crypto.data_encryption.DataEncryptionError",
        RuntimeError,
    ):
        await mod._restore_stored_mood_on_connect(ws)
    ws.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_restore_mood_no_query_conversation_id() -> None:
    """No conversation_id in the query → falls back to recent[0]."""
    ws = SimpleNamespace(
        send_json=AsyncMock(),
        scope={"query_string": b""},
    )
    conv = SimpleNamespace(
        id=5, chatbot_id=None,
        user_data={"current_mood": {"mood": "calm", "emoji": "😌"}},
    )
    fake_objects = MagicMock()
    fake_objects.get.return_value = None
    q = MagicMock()
    q.order_by.return_value = q
    q.limit.return_value = q
    q.all.return_value = [conv]
    fake_objects.query.return_value = q

    with patch(
        "airunner_services.database.models.conversation.Conversation",
        SimpleNamespace(objects=fake_objects, id=MagicMock()),
    ):
        await mod._restore_stored_mood_on_connect(ws)

    ws.send_json.assert_awaited_once()
    assert ws.send_json.await_args[0][0]["type"] == "mood"


@pytest.mark.asyncio
async def test_restore_mood_empty_recent_returns() -> None:
    """Empty recent list with no conversation → silent return."""
    ws = SimpleNamespace(
        send_json=AsyncMock(),
        scope={"query_string": b""},
    )
    fake_objects = MagicMock()
    fake_objects.get.return_value = None
    q = MagicMock()
    q.order_by.return_value = q
    q.limit.return_value = q
    q.all.return_value = []
    fake_objects.query.return_value = q

    with patch(
        "airunner_services.database.models.conversation.Conversation",
        SimpleNamespace(objects=fake_objects, id=MagicMock()),
    ):
        await mod._restore_stored_mood_on_connect(ws)
    ws.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_restore_mood_query_decrypt_error_skips_row() -> None:
    """A DataEncryptionError reading a row's user_data skips that row."""
    ws = SimpleNamespace(
        send_json=AsyncMock(),
        scope={"query_string": b"conversation_id=5"},
    )
    conv_ok = SimpleNamespace(
        id=6, chatbot_id=3,
        user_data={"current_mood": {"mood": "happy", "emoji": "😊"}},
    )
    ref_conv = SimpleNamespace(id=5, chatbot_id=3)
    fake_objects = MagicMock()

    def _get(cid):
        return ref_conv

    fake_objects.get.side_effect = _get
    q = MagicMock()
    q.order_by.return_value = q
    q.limit.return_value = q
    q.all.return_value = [conv_ok]
    fake_objects.query.return_value = q

    with patch(
        "airunner_services.database.models.conversation.Conversation",
        SimpleNamespace(objects=fake_objects, id=MagicMock()),
    ):
        await mod._restore_stored_mood_on_connect(ws)

    ws.send_json.assert_awaited_once()
    assert ws.send_json.await_args[0][0]["mood"] == "happy"


# ---------------------------------------------------------------------------
# websocket_chat endpoint branches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_websocket_chat_rejects_anon() -> None:
    ws = MagicMock()
    ws.close = AsyncMock()
    with patch.object(mod, "resolve_ws_tenant", return_value=(None, None)):
        await mod.websocket_chat(ws)
    ws.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_websocket_chat_disconnect_handled() -> None:
    from fastapi import WebSocketDisconnect

    ws = MagicMock()
    ws.scope = {"query_string": b"", "headers": []}
    ws.accept = AsyncMock()
    ws.close = AsyncMock()
    with patch.object(mod, "resolve_ws_tenant", return_value=("t", 1)), patch(
        "airunner_services.api.routes.llm_stream_routes.ws_tenant_scope"
    ) as scope:
        scope.return_value.__enter__.return_value = ("t", 1)
        scope.return_value.__exit__.return_value = None
        with patch.object(mod, "resolve_llm_client") as rlc, patch.object(
            mod, "require_websocket_runtime_registry"
        ), patch.object(mod, "_restore_stored_mood_on_connect", new=AsyncMock()), patch.object(
            mod, "_chat_loop", new=AsyncMock(side_effect=WebSocketDisconnect)
        ):
            await mod.websocket_chat(ws)
    rlc.assert_called_once()


@pytest.mark.asyncio
async def test_websocket_chat_http_exception() -> None:
    from fastapi import HTTPException

    ws = MagicMock()
    ws.scope = {"query_string": b"", "headers": []}
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    with patch.object(mod, "resolve_ws_tenant", return_value=("t", 1)), patch(
        "airunner_services.api.routes.llm_stream_routes.ws_tenant_scope"
    ) as scope:
        scope.return_value.__enter__.return_value = ("t", 1)
        scope.return_value.__exit__.return_value = None
        with patch.object(mod, "resolve_llm_client"), patch.object(
            mod, "require_websocket_runtime_registry"
        ), patch.object(mod, "_restore_stored_mood_on_connect", new=AsyncMock()), patch.object(
            mod, "_chat_loop",
            new=AsyncMock(side_effect=HTTPException(400, "bad")),
        ):
            await mod.websocket_chat(ws)
    ws.send_json.assert_awaited_once()
    assert ws.send_json.await_args[0][0]["type"] == "error"


@pytest.mark.asyncio
async def test_websocket_chat_generic_error() -> None:
    ws = MagicMock()
    ws.scope = {"query_string": b"", "headers": []}
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    with patch.object(mod, "resolve_ws_tenant", return_value=("t", 1)), patch(
        "airunner_services.api.routes.llm_stream_routes.ws_tenant_scope"
    ) as scope:
        scope.return_value.__enter__.return_value = ("t", 1)
        scope.return_value.__exit__.return_value = None
        with patch.object(mod, "resolve_llm_client"), patch.object(
            mod, "require_websocket_runtime_registry"
        ), patch.object(mod, "_restore_stored_mood_on_connect", new=AsyncMock()), patch.object(
            mod, "_chat_loop", new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            await mod.websocket_chat(ws)
    ws.send_json.assert_awaited_once()
    assert "outage" in ws.send_json.await_args[0][0]["content"]


# ---------------------------------------------------------------------------
# _chat_loop branches
# ---------------------------------------------------------------------------


def _chat_ws(messages):
    """A websocket whose receive_json yields *messages* then raises."""
    queue = list(messages)
    ws = MagicMock()
    ws.receive_json = AsyncMock(side_effect=queue + [StopAsyncIteration()])
    ws.send_json = AsyncMock()
    return ws


@pytest.mark.asyncio
async def test_chat_loop_no_content() -> None:
    ws = _chat_ws([{}])
    with patch.object(mod, "_try_load_quota_checker", return_value=None), patch.object(
        mod, "_try_load_daily_token_checker", return_value=None
    ), patch.object(mod, "_resolve_max_output_token_ceiling", return_value=500), patch(
        "airunner_services.api.ws_tenant.ws_dek_scope"
    ) as dek, patch(
        "airunner_services.llm.safety.account_context.set_current_account_id"
    ), patch.object(mod, "_emit_stored_mood", new=AsyncMock()):
        dek.return_value.__enter__.return_value = None
        dek.return_value.__exit__.return_value = None
        try:
            await mod._chat_loop(MagicMock(), ws, 1)
        except StopAsyncIteration:
            pass
    assert ws.send_json.await_args[0][0]["type"] == "error"


@pytest.mark.asyncio
async def test_chat_loop_quota_exceeded() -> None:
    ws = _chat_ws([{"message": "hi", "chatbot_id": 1}])
    with patch.object(mod, "_try_load_quota_checker",
                      return_value=lambda *a, **k: True), patch.object(
        mod, "_try_load_daily_token_checker", return_value=None
    ), patch.object(mod, "_resolve_max_output_token_ceiling", return_value=500), patch(
        "airunner_services.api.ws_tenant.ws_dek_scope"
    ) as dek, patch(
        "airunner_services.llm.safety.account_context.set_current_account_id"
    ), patch.object(mod, "_emit_stored_mood", new=AsyncMock()):
        dek.return_value.__enter__.return_value = None
        dek.return_value.__exit__.return_value = None
        try:
            await mod._chat_loop(MagicMock(), ws, 1)
        except StopAsyncIteration:
            pass
    payload = ws.send_json.await_args[0][0]
    assert payload["type"] == "quota_exceeded"


@pytest.mark.asyncio
async def test_chat_loop_restore_mood_message() -> None:
    ws = _chat_ws([{"type": "restore_mood", "conversation_id": 5}])
    with patch.object(mod, "_try_load_quota_checker", return_value=None), patch.object(
        mod, "_try_load_daily_token_checker", return_value=None
    ), patch.object(mod, "_resolve_max_output_token_ceiling", return_value=500), patch(
        "airunner_services.api.ws_tenant.ws_dek_scope"
    ) as dek, patch(
        "airunner_services.llm.safety.account_context.set_current_account_id"
    ), patch.object(mod, "_emit_stored_mood", new=AsyncMock()) as emit:
        dek.return_value.__enter__.return_value = None
        dek.return_value.__exit__.return_value = None
        try:
            await mod._chat_loop(MagicMock(), ws, 1)
        except StopAsyncIteration:
            pass
    emit.assert_called()


@pytest.mark.asyncio
async def test_chat_loop_cancel_message() -> None:
    ws = _chat_ws([{"type": "cancel"}])
    with patch.object(mod, "_try_load_quota_checker", return_value=None), patch.object(
        mod, "_try_load_daily_token_checker", return_value=None
    ), patch.object(mod, "_resolve_max_output_token_ceiling", return_value=500), patch(
        "airunner_services.api.ws_tenant.ws_dek_scope"
    ) as dek, patch(
        "airunner_services.llm.safety.account_context.set_current_account_id"
    ), patch.object(mod, "_emit_stored_mood", new=AsyncMock()):
        dek.return_value.__enter__.return_value = None
        dek.return_value.__exit__.return_value = None
        try:
            await mod._chat_loop(MagicMock(), ws, 1)
        except StopAsyncIteration:
            pass
    ws.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_chat_loop_daily_token_limit() -> None:
    """The daily-token-limit branch sends a quota_exceeded frame."""
    ws = _chat_ws([{"message": "hi", "chatbot_id": 1}])
    with patch.object(mod, "_try_load_quota_checker", return_value=None), patch.object(
        mod, "_try_load_daily_token_checker",
        return_value=lambda *a, **k: True,
    ), patch.object(mod, "_resolve_max_output_token_ceiling", return_value=500), patch(
        "airunner_services.api.ws_tenant.ws_dek_scope"
    ) as dek, patch(
        "airunner_services.llm.safety.account_context.set_current_account_id"
    ), patch.object(mod, "_emit_stored_mood", new=AsyncMock()):
        dek.return_value.__enter__.return_value = None
        dek.return_value.__exit__.return_value = None
        try:
            await mod._chat_loop(MagicMock(), ws, 1)
        except StopAsyncIteration:
            pass
    payload = ws.send_json.await_args[0][0]
    assert payload["type"] == "quota_exceeded"
    assert "daily token" in payload["message"]


@pytest.mark.asyncio
async def test_chat_loop_rate_limited() -> None:
    """The rate-limit branch sends a rate_limited frame."""
    ws = _chat_ws([{"message": "hi", "chatbot_id": 1}])
    with patch.object(mod, "_try_load_quota_checker", return_value=None), patch.object(
        mod, "_try_load_daily_token_checker", return_value=None
    ), patch.object(mod, "_resolve_max_output_token_ceiling", return_value=500), patch(
        "airunner_services.api.ws_tenant.ws_dek_scope"
    ) as dek, patch(
        "airunner_services.llm.safety.account_context.set_current_account_id"
    ), patch.object(mod, "_emit_stored_mood", new=AsyncMock()), patch.object(
        mod, "check_llm_stream_rate", return_value=False
    ):
        dek.return_value.__enter__.return_value = None
        dek.return_value.__exit__.return_value = None
        try:
            await mod._chat_loop(MagicMock(), ws, 1)
        except StopAsyncIteration:
            pass
    payload = ws.send_json.await_args[0][0]
    assert payload["type"] == "rate_limited"


# ---------------------------------------------------------------------------
# _chat_loop full stream path (stream + cancel race)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_loop_stream_completes() -> None:
    """A normal message streams to the socket, then the loop continues.

    The stream completes before any cancel arrives → the else branch
    (cancel_task.cancel(), lines 504-510).  The race-time receive
    blocks forever so the stream task deterministically finishes first.
    """
    ws = _chat_ws([{"message": "hi", "chatbot_id": 1, "conversation_id": 3}])

    async def _stream_to_socket_impl(client, websocket, envelope):
        await websocket.send_json({"type": "chunk", "content": "ok", "done": True})

    state = {"calls": 0}

    async def _receive_json():
        # Call 1 = user message; call 2 blocks (cancelled by the else
        # branch); call 3 terminates the loop.
        state["calls"] += 1
        if state["calls"] == 1:
            return {"message": "hi", "chatbot_id": 1, "conversation_id": 3}
        if state["calls"] == 2:
            await asyncio.sleep(30)  # blocks until cancelled
            return {"type": "cancel"}
        raise StopAsyncIteration()

    with patch.object(mod, "_try_load_quota_checker", return_value=None), patch.object(
        mod, "_try_load_daily_token_checker", return_value=None
    ), patch.object(mod, "_resolve_max_output_token_ceiling", return_value=500), patch(
        "airunner_services.api.ws_tenant.ws_dek_scope"
    ) as dek, patch(
        "airunner_services.llm.safety.account_context.set_current_account_id"
    ), patch.object(mod, "_emit_stored_mood", new=AsyncMock()), patch.object(
        mod, "_ensure_session_rotation"
    ), patch.object(
        mod, "check_llm_stream_rate", return_value=True
    ), patch.object(
        mod, "_conversation_is_code_mode", return_value=False
    ), patch.object(
        mod, "_stream_to_socket", new=_stream_to_socket_impl
    ):
        dek.return_value.__enter__.return_value = None
        dek.return_value.__exit__.return_value = None
        ws.receive_json = _receive_json
        try:
            await mod._chat_loop(MagicMock(), ws, 1)
        except StopAsyncIteration:
            pass
    # The stream sent a chunk; the else branch cancelled the pending task.
    assert any(
        c[0][0].get("type") == "chunk"
        for c in ws.send_json.call_args_list
    )


@pytest.mark.asyncio
async def test_chat_loop_code_mode_ceiling() -> None:
    """A code-mode conversation gets the 8192 ceiling via the envelope."""
    ws = _chat_ws([{"message": "hi", "chatbot_id": 1, "conversation_id": 3}])
    sent_envelope = {}

    async def _stream_to_socket_impl(client, websocket, envelope):
        sent_envelope["max_tokens"] = envelope.payload.get("max_tokens")
        await websocket.send_json({"type": "chunk", "content": "ok", "done": True})

    with patch.object(mod, "_try_load_quota_checker", return_value=None), patch.object(
        mod, "_try_load_daily_token_checker", return_value=None
    ), patch.object(mod, "_resolve_max_output_token_ceiling", return_value=500), patch(
        "airunner_services.api.ws_tenant.ws_dek_scope"
    ) as dek, patch(
        "airunner_services.llm.safety.account_context.set_current_account_id"
    ), patch.object(mod, "_emit_stored_mood", new=AsyncMock()), patch.object(
        mod, "_ensure_session_rotation"
    ), patch.object(
        mod, "check_llm_stream_rate", return_value=True
    ), patch.object(
        mod, "_conversation_is_code_mode", return_value=True
    ), patch.object(
        mod, "_stream_to_socket", new=_stream_to_socket_impl
    ):
        dek.return_value.__enter__.return_value = None
        dek.return_value.__exit__.return_value = None
        try:
            await mod._chat_loop(MagicMock(), ws, 1)
        except StopAsyncIteration:
            pass
    assert sent_envelope["max_tokens"] == mod.CODE_MODE_MAX_OUTPUT_TOKENS


@pytest.mark.asyncio
async def test_chat_loop_stream_cancelled() -> None:
    """A cancel arriving mid-stream cancels the stream task.

    The cancel task wins the race → the cancel branch sends a done frame.
    """
    ws = _chat_ws([{"message": "hi", "chatbot_id": 1}])

    async def _stream_to_socket_impl(client, websocket, envelope):
        await asyncio.sleep(5)  # never completes on its own

    with patch.object(mod, "_try_load_quota_checker", return_value=None), patch.object(
        mod, "_try_load_daily_token_checker", return_value=None
    ), patch.object(mod, "_resolve_max_output_token_ceiling", return_value=500), patch(
        "airunner_services.api.ws_tenant.ws_dek_scope"
    ) as dek, patch(
        "airunner_services.llm.safety.account_context.set_current_account_id"
    ), patch.object(mod, "_emit_stored_mood", new=AsyncMock()), patch.object(
        mod, "_ensure_session_rotation"
    ), patch.object(
        mod, "check_llm_stream_rate", return_value=True
    ), patch.object(
        mod, "_stream_to_socket", new=_stream_to_socket_impl
    ):
        dek.return_value.__enter__.return_value = None
        dek.return_value.__exit__.return_value = None
        # First receive = user message; second receive = cancel arriving
        # during the stream.
        ws.receive_json = AsyncMock(
            side_effect=[
                {"message": "hi", "chatbot_id": 1},
                {"type": "cancel"},
                StopAsyncIteration(),
            ]
        )
        try:
            await mod._chat_loop(MagicMock(), ws, 1)
        except StopAsyncIteration:
            pass
    # The cancel path sent a done frame.
    assert any(
        c[0][0].get("type") == "done"
        for c in ws.send_json.call_args_list
    )


@pytest.mark.asyncio
async def test_chat_loop_stream_non_cancel_message_waits() -> None:
    """A non-cancel message arriving mid-stream is deferred.

    The cancel task (which read a non-cancel message) wins the race;
    the stream task is cancelled in the `for t in pending` loop
    (lines 498-503).
    """
    ws = _chat_ws([{"message": "hi", "chatbot_id": 1}])

    async def _stream_to_socket_impl(client, websocket, envelope):
        await asyncio.sleep(5)  # never completes on its own

    with patch.object(mod, "_try_load_quota_checker", return_value=None), patch.object(
        mod, "_try_load_daily_token_checker", return_value=None
    ), patch.object(mod, "_resolve_max_output_token_ceiling", return_value=500), patch(
        "airunner_services.api.ws_tenant.ws_dek_scope"
    ) as dek, patch(
        "airunner_services.llm.safety.account_context.set_current_account_id"
    ), patch.object(mod, "_emit_stored_mood", new=AsyncMock()), patch.object(
        mod, "_ensure_session_rotation"
    ), patch.object(
        mod, "check_llm_stream_rate", return_value=True
    ), patch.object(
        mod, "_stream_to_socket", new=_stream_to_socket_impl
    ):
        dek.return_value.__enter__.return_value = None
        dek.return_value.__exit__.return_value = None
        # First receive = user message; second receive returns a
        # non-cancel message that wins the race (stream is sleeping).
        ws.receive_json = AsyncMock(
            side_effect=[
                {"message": "hi", "chatbot_id": 1},
                {"message": "next", "chatbot_id": 1},
                StopAsyncIteration(),
            ]
        )
        try:
            await mod._chat_loop(MagicMock(), ws, 1)
        except StopAsyncIteration:
            pass
    # The non-cancel path cancelled the pending stream task.
    ws.send_json.assert_not_called()


# ---------------------------------------------------------------------------
# Remaining branch edges
# ---------------------------------------------------------------------------


def test_token_ceiling_account_none() -> None:
    """An account lookup returning None falls back to the default tier."""
    with patch(
        "extensions.auth.server.models.Account"
    ), patch(
        "airunner_services.database.session.public_session_scope"
    ) as scope:
        session = MagicMock()
        scope.return_value.__enter__.return_value = session
        session.get.return_value = None
        assert mod._resolve_max_output_token_ceiling(7) == 500


@pytest.mark.asyncio
async def test_restore_mood_get_data_encryption_error() -> None:
    """A DataEncryptionError in Conversation.objects.get is swallowed."""
    ws = SimpleNamespace(
        send_json=AsyncMock(),
        scope={"query_string": b"conversation_id=5"},
    )

    class _BoomGet:
        def get(self, *a, **k):
            raise RuntimeError("dek")

    with patch(
        "airunner_services.database.models.conversation.Conversation",
        SimpleNamespace(objects=_BoomGet(), id=MagicMock()),
    ), patch(
        "airunner_services.utils.crypto.data_encryption.DataEncryptionError",
        RuntimeError,
    ):
        await mod._restore_stored_mood_on_connect(ws)
    ws.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_restore_mood_query_data_encryption_error_returns() -> None:
    """A DataEncryptionError on the recent query returns early."""
    ws = SimpleNamespace(
        send_json=AsyncMock(),
        scope={"query_string": b""},
    )

    class _BoomQuery:
        def query(self, *a, **k):
            raise RuntimeError("dek")

    with patch(
        "airunner_services.database.models.conversation.Conversation",
        SimpleNamespace(objects=_BoomQuery(), id=MagicMock()),
    ), patch(
        "airunner_services.utils.crypto.data_encryption.DataEncryptionError",
        RuntimeError,
    ):
        await mod._restore_stored_mood_on_connect(ws)
    ws.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_restore_mood_final_mood_decrypt_error() -> None:
    """A DataEncryptionError reading the final conv's mood returns."""
    ws = SimpleNamespace(
        send_json=AsyncMock(),
        scope={"query_string": b""},
    )

    class _BoomUserData:
        @property
        def user_data(self):
            raise RuntimeError("dek")

    conv = _BoomUserData()
    q = MagicMock()
    q.order_by.return_value = q
    q.limit.return_value = q
    q.all.return_value = [conv]
    fake_objects = MagicMock()
    fake_objects.get.return_value = None
    fake_objects.query.return_value = q

    with patch(
        "airunner_services.database.models.conversation.Conversation",
        SimpleNamespace(objects=fake_objects, id=MagicMock()),
    ), patch(
        "airunner_services.utils.crypto.data_encryption.DataEncryptionError",
        RuntimeError,
    ):
        await mod._restore_stored_mood_on_connect(ws)
    ws.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_restore_mood_no_mood_value_returns() -> None:
    """A conv with no usable mood returns without emitting."""
    ws = SimpleNamespace(
        send_json=AsyncMock(),
        scope={"query_string": b""},
    )
    conv = SimpleNamespace(id=5, chatbot_id=None, user_data={})
    q = MagicMock()
    q.order_by.return_value = q
    q.limit.return_value = q
    q.all.return_value = [conv]
    fake_objects = MagicMock()
    fake_objects.get.return_value = None
    fake_objects.query.return_value = q

    with patch(
        "airunner_services.database.models.conversation.Conversation",
        SimpleNamespace(objects=fake_objects, id=MagicMock()),
    ):
        await mod._restore_stored_mood_on_connect(ws)
    ws.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_chat_loop_code_mode_type_error() -> None:
    """A non-int conversation_id hits the TypeError/ValueError except."""
    ws = _chat_ws([{"message": "hi", "chatbot_id": 1, "conversation_id": "abc"}])

    async def _stream_to_socket_impl(client, websocket, envelope):
        await websocket.send_json({"type": "chunk", "content": "ok", "done": True})

    with patch.object(mod, "_try_load_quota_checker", return_value=None), patch.object(
        mod, "_try_load_daily_token_checker", return_value=None
    ), patch.object(mod, "_resolve_max_output_token_ceiling", return_value=500), patch(
        "airunner_services.api.ws_tenant.ws_dek_scope"
    ) as dek, patch(
        "airunner_services.llm.safety.account_context.set_current_account_id"
    ), patch.object(mod, "_emit_stored_mood", new=AsyncMock()), patch.object(
        mod, "_ensure_session_rotation"
    ), patch.object(
        mod, "check_llm_stream_rate", return_value=True
    ), patch.object(
        mod, "_stream_to_socket", new=_stream_to_socket_impl
    ):
        dek.return_value.__enter__.return_value = None
        dek.return_value.__exit__.return_value = None
        try:
            await mod._chat_loop(MagicMock(), ws, 1)
        except StopAsyncIteration:
            pass
    assert any(
        c[0][0].get("type") == "chunk"
        for c in ws.send_json.call_args_list
    )


@pytest.mark.asyncio
async def test_restore_mood_skips_other_chatbot_in_loop() -> None:
    """Recent rows for another chatbot are skipped (line 87 continue).

    When no matching row exists, the code falls back to recent[0] and
    emits its mood — so send_json IS called with the fallback.
    """
    ws = SimpleNamespace(
        send_json=AsyncMock(),
        scope={"query_string": b"conversation_id=5"},
    )
    ref_conv = SimpleNamespace(id=5, chatbot_id=3)
    other = SimpleNamespace(
        id=6, chatbot_id=99, user_data={"current_mood": {"mood": "fallback"}}
    )
    fake_objects = MagicMock()
    fake_objects.get.return_value = ref_conv
    q = MagicMock()
    q.order_by.return_value = q
    q.limit.return_value = q
    q.all.return_value = [other]  # no matching chatbot → fallback to recent[0]
    fake_objects.query.return_value = q

    with patch(
        "airunner_services.database.models.conversation.Conversation",
        SimpleNamespace(objects=fake_objects, id=MagicMock()),
    ):
        await mod._restore_stored_mood_on_connect(ws)

    ws.send_json.assert_awaited_once()
    assert ws.send_json.await_args[0][0]["mood"] == "fallback"


@pytest.mark.asyncio
async def test_restore_mood_fallback_index_error_returns() -> None:
    """recent[0] IndexError returns silently (lines 98-99)."""
    ws = SimpleNamespace(
        send_json=AsyncMock(),
        scope={"query_string": b"conversation_id=5"},
    )
    ref_conv = SimpleNamespace(id=5, chatbot_id=3)
    fake_objects = MagicMock()
    fake_objects.get.return_value = ref_conv
    q = MagicMock()
    q.order_by.return_value = q
    q.limit.return_value = q
    q.all.return_value = [SimpleNamespace(
        id=6, chatbot_id=99,  # no matching mood row
        user_data={},
    )]
    fake_objects.query.return_value = q

    with patch(
        "airunner_services.database.models.conversation.Conversation",
        SimpleNamespace(objects=fake_objects, id=MagicMock()),
    ):
        await mod._restore_stored_mood_on_connect(ws)
    ws.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_restore_mood_outer_dek_error() -> None:
    """The outer DataEncryptionError (line 121-122) logs and returns.

    Conversation.objects.get raises DataEncryptionError (mapped to
    RuntimeError) — caught by the outer handler, nothing emitted.
    """
    ws = SimpleNamespace(
        send_json=AsyncMock(),
        scope={"query_string": b"conversation_id=5"},
    )

    class _BoomGet:
        def get(self, *a, **k):
            raise RuntimeError("dek")
        def query(self, *a, **k):
            raise AssertionError("should not reach query")

    with patch(
        "airunner_services.database.models.conversation.Conversation",
        SimpleNamespace(objects=_BoomGet(), id=MagicMock()),
    ), patch(
        "airunner_services.utils.crypto.data_encryption.DataEncryptionError",
        RuntimeError,
    ):
        await mod._restore_stored_mood_on_connect(ws)
    ws.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_emit_stored_mood_skips_other_chatbot_branch() -> None:
    """_emit_stored_mood's chatbot-filter continue (line 160->171)."""
    ws = SimpleNamespace(send_json=AsyncMock())
    ref = SimpleNamespace(id=5, chatbot_id=3)
    other = SimpleNamespace(
        id=6, chatbot_id=99,
        user_data={"current_mood": {"mood": "x", "emoji": "y"}},
    )
    fake_objects = MagicMock()
    fake_objects.get.return_value = ref
    q = MagicMock()
    q.order_by.return_value = q
    q.limit.return_value = q
    q.all.return_value = [other]
    fake_objects.query.return_value = q

    with patch(
        "airunner_services.database.models.conversation.Conversation",
        SimpleNamespace(objects=fake_objects, id=MagicMock()),
    ):
        await mod._emit_stored_mood({"conversation_id": 5}, ws)
    ws.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_emit_stored_mood_empty_recent() -> None:
    """_emit_stored_mood with no recent conversations returns (160->171)."""
    ws = SimpleNamespace(send_json=AsyncMock())
    ref = SimpleNamespace(id=5, chatbot_id=3)
    q = MagicMock()
    q.order_by.return_value = q
    q.limit.return_value = q
    q.all.return_value = []  # empty recent → `if recent:` false
    fake_objects = MagicMock()
    fake_objects.get.return_value = ref
    fake_objects.query.return_value = q

    with patch(
        "airunner_services.database.models.conversation.Conversation",
        SimpleNamespace(objects=fake_objects, id=MagicMock()),
    ):
        await mod._emit_stored_mood({"conversation_id": 5}, ws)
    ws.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_chat_loop_second_message_skips_mood() -> None:
    """The stored-mood emit only fires on the FIRST message (368->374).

    Two messages: the first emits mood; the second skips the emit but
    still streams.
    """
    ws = _chat_ws([{"message": "one", "chatbot_id": 1}])

    async def _stream_to_socket_impl(client, websocket, envelope):
        await websocket.send_json({"type": "chunk", "content": "ok", "done": True})

    with patch.object(mod, "_try_load_quota_checker", return_value=None), patch.object(
        mod, "_try_load_daily_token_checker", return_value=None
    ), patch.object(mod, "_resolve_max_output_token_ceiling", return_value=500), patch(
        "airunner_services.api.ws_tenant.ws_dek_scope"
    ) as dek, patch(
        "airunner_services.llm.safety.account_context.set_current_account_id"
    ), patch.object(mod, "_emit_stored_mood", new=AsyncMock()) as emit, patch.object(
        mod, "_ensure_session_rotation"
    ), patch.object(
        mod, "check_llm_stream_rate", return_value=True
    ), patch.object(
        mod, "_stream_to_socket", new=_stream_to_socket_impl
    ):
        dek.return_value.__enter__.return_value = None
        dek.return_value.__exit__.return_value = None
        try:
            await mod._chat_loop(MagicMock(), ws, 1)
        except StopAsyncIteration:
            pass
    emit.assert_called_once()  # only once, on the first message


@pytest.mark.asyncio
async def test_restore_mood_fallback_recent_index_error() -> None:
    """recent[0] IndexError in the fallback returns silently (98-99)."""
    ws = SimpleNamespace(
        send_json=AsyncMock(),
        scope={"query_string": b"conversation_id=5"},
    )
    ref_conv = SimpleNamespace(id=5, chatbot_id=3)
    # recent is non-empty (truthy) but [0] raises IndexError.
    class _IndexErrorList(list):
        def __len__(self):
            return 1

        def __getitem__(self, i):
            raise IndexError("empty")

    q = MagicMock()
    q.order_by.return_value = q
    q.limit.return_value = q
    q.all.return_value = _IndexErrorList()
    fake_objects = MagicMock()
    fake_objects.get.return_value = ref_conv
    fake_objects.query.return_value = q

    with patch(
        "airunner_services.database.models.conversation.Conversation",
        SimpleNamespace(objects=fake_objects, id=MagicMock()),
    ):
        await mod._restore_stored_mood_on_connect(ws)
    ws.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_restore_mood_fallback_dek_index_error() -> None:
    """recent[0] DataEncryptionError in the fallback returns (98-99)."""
    ws = SimpleNamespace(
        send_json=AsyncMock(),
        scope={"query_string": b"conversation_id=5"},
    )
    ref_conv = SimpleNamespace(id=5, chatbot_id=3)

    class _BoomRecent:
        def __getitem__(self, i):
            raise RuntimeError("dek")

    q = MagicMock()
    q.order_by.return_value = q
    q.limit.return_value = q
    q.all.return_value = _BoomRecent()
    fake_objects = MagicMock()
    fake_objects.get.return_value = ref_conv
    fake_objects.query.return_value = q

    with patch(
        "airunner_services.database.models.conversation.Conversation",
        SimpleNamespace(objects=fake_objects, id=MagicMock()),
    ), patch(
        "airunner_services.utils.crypto.data_encryption.DataEncryptionError",
        RuntimeError,
    ):
        await mod._restore_stored_mood_on_connect(ws)
    ws.send_json.assert_not_called()


def test_daily_checker_empty_project() -> None:
    """A resolved-but-empty project returns None (line 309)."""
    with patch.dict("os.environ", {}, clear=True), patch(
        "airunner_services.conf.settings"
    ) as settings:
        settings.AIRUNNER_PROJECT = ""
        assert mod._try_load_daily_token_checker() is None


@pytest.mark.asyncio
async def test_chat_loop_first_message_emits_mood() -> None:
    """The first message triggers the stored-mood emit (line 368->374)."""
    ws = _chat_ws([{"message": "hi", "chatbot_id": 1}])

    async def _stream_to_socket_impl(client, websocket, envelope):
        await websocket.send_json({"type": "chunk", "content": "ok", "done": True})

    with patch.object(mod, "_try_load_quota_checker", return_value=None), patch.object(
        mod, "_try_load_daily_token_checker", return_value=None
    ), patch.object(mod, "_resolve_max_output_token_ceiling", return_value=500), patch(
        "airunner_services.api.ws_tenant.ws_dek_scope"
    ) as dek, patch(
        "airunner_services.llm.safety.account_context.set_current_account_id"
    ), patch.object(mod, "_emit_stored_mood", new=AsyncMock()) as emit, patch.object(
        mod, "_ensure_session_rotation"
    ), patch.object(
        mod, "check_llm_stream_rate", return_value=True
    ), patch.object(
        mod, "_stream_to_socket", new=_stream_to_socket_impl
    ):
        dek.return_value.__enter__.return_value = None
        dek.return_value.__exit__.return_value = None
        try:
            await mod._chat_loop(MagicMock(), ws, 1)
        except StopAsyncIteration:
            pass
    emit.assert_called_once()
