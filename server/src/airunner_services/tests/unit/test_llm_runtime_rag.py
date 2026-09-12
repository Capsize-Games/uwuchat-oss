"""Unit tests for llm_runtime_rag websocket payload conversion.

Covers ``websocket_chunk`` for every delta shape (failed, tool_status,
mood, system, thinking, plain chunk with tool_calls/call_chain_id),
``_websocket_tool_or_mood``, and the WS-payload parsing helpers
(``_parse_raw_messages``, ``_build_envelope_metadata``).  Also covers
the RAG metadata/persist helpers with mocked DB objects.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from airunner_services.api.routes import llm_runtime_rag as mod
from airunner_services.ipc.messages import EnvelopeStatus, StreamDelta


def _delta(
    *,
    status=EnvelopeStatus.SUCCEEDED,
    final: bool = False,
    delta: dict | None = None,
    metadata: dict | None = None,
) -> StreamDelta:
    """Build a StreamDelta with the given shape."""
    return StreamDelta(
        request_id="req-1",
        status=status,
        final=final,
        delta=delta or {},
        metadata=metadata or {},
    )


# ---------------------------------------------------------------------------
# websocket_chunk
# ---------------------------------------------------------------------------


def test_websocket_chunk_failed_status() -> None:
    payload = mod.websocket_chunk(
        _delta(
            status=EnvelopeStatus.FAILED,
            metadata={"error": "LLM runtime failed"},
        )
    )
    assert payload["type"] == "error"
    assert payload["content"] == "LLM runtime failed"
    assert payload["done"] is True


def test_websocket_chunk_failed_default_error() -> None:
    payload = mod.websocket_chunk(_delta(status=EnvelopeStatus.FAILED))
    assert payload["content"] == "LLM runtime failed"


def test_websocket_chunk_tool_status() -> None:
    payload = mod.websocket_chunk(
        _delta(
            metadata={"message_type": "tool_status"},
            delta={
                "content": (
                    '{"tool_id":"tc-1","tool_name":"execute_command",'
                    '"status":"completed"}'
                )
            },
        )
    )
    assert payload["type"] == "tool_status"
    assert payload["tool_id"] == "tc-1"
    assert payload["tool_name"] == "execute_command"
    assert payload["done"] is False


def test_websocket_chunk_tool_status_invalid_json() -> None:
    payload = mod.websocket_chunk(
        _delta(
            metadata={"message_type": "tool_status"},
            delta={"content": "{not json"},
        )
    )
    assert payload["type"] == "tool_status"
    assert payload["done"] is False


def test_websocket_chunk_mood() -> None:
    payload = mod.websocket_chunk(
        _delta(
            metadata={"message_type": "mood"},
            delta={
                "content": '{"mood":"happy","emoji":"😊",'
                '"kaomoji":"(＾▽＾)"}'
            },
        )
    )
    assert payload["type"] == "mood"
    assert payload["mood"] == "happy"
    assert payload["done"] is False


def test_websocket_chunk_system_message() -> None:
    payload = mod.websocket_chunk(
        _delta(
            metadata={"message_type": "system"},
            delta={"content": "error text"},
            final=True,
        )
    )
    assert payload["type"] == "error"
    assert payload["error"] == "error text"
    assert payload["done"] is True


def test_websocket_chunk_thinking_type() -> None:
    payload = mod.websocket_chunk(
        _delta(
            metadata={"message_type": "thinking"},
            delta={"content": "reasoning"},
            final=False,
        )
    )
    assert payload["type"] == "thinking"
    assert payload["content"] == "reasoning"
    assert payload["done"] is False


def test_websocket_chunk_plain_chunk() -> None:
    payload = mod.websocket_chunk(
        _delta(delta={"content": "hello"}, final=False)
    )
    assert payload["type"] == "chunk"
    assert payload["content"] == "hello"
    assert payload["done"] is False


def test_websocket_chunk_with_tool_calls() -> None:
    tool_calls = [{"name": "execute_command", "id": "tc-1"}]
    payload = mod.websocket_chunk(
        _delta(delta={"content": "", "tool_calls": tool_calls})
    )
    assert payload["tool_calls"] == tool_calls


def test_websocket_chunk_final_with_call_chain_id() -> None:
    payload = mod.websocket_chunk(
        _delta(
            delta={"content": "done"},
            final=True,
            metadata={"call_chain_id": "chain-9"},
        )
    )
    assert payload["call_chain_id"] == "chain-9"


def test_websocket_chunk_final_without_call_chain_id() -> None:
    payload = mod.websocket_chunk(_delta(delta={"content": "done"}, final=True))
    assert "call_chain_id" not in payload


# ---------------------------------------------------------------------------
# _websocket_tool_or_mood
# ---------------------------------------------------------------------------


def test_websocket_tool_or_mood_parses_json() -> None:
    payload = mod._websocket_tool_or_mood(
        _delta(
            metadata={"message_type": "tool_status"},
            delta={"content": '{"status":"starting"}'},
        ),
        "tool_status",
    )
    assert payload == {"type": "tool_status", "done": False, "status": "starting"}


def test_websocket_tool_or_mood_bad_json_defaults_empty() -> None:
    payload = mod._websocket_tool_or_mood(
        _delta(
            metadata={"message_type": "mood"},
            delta={"content": "nope"},
        ),
        "mood",
    )
    assert payload == {"type": "mood", "done": False}


# ---------------------------------------------------------------------------
# _parse_raw_messages / _build_envelope_metadata
# ---------------------------------------------------------------------------


def test_parse_raw_messages_uses_messages_list() -> None:
    raw = [{"role": "user", "content": "hi"}]
    assert mod._parse_raw_messages({"messages": raw}) == raw


def test_parse_raw_messages_falls_back_to_message() -> None:
    assert mod._parse_raw_messages({"message": "  hello  "}) == [
        {"role": "user", "content": "hello"}
    ]


def test_build_envelope_metadata_all_fields() -> None:
    meta = mod._build_envelope_metadata(
        {
            "gguf_runtime_profile": "cpu",
            "conversation_id": 5,
            "chatbot_id": 3,
            "user_local_time": "Mon 10:00",
        }
    )
    assert meta["gguf_runtime_profile"] == "cpu"
    assert meta["conversation_id"] == 5
    assert meta["chatbot_id"] == 3
    assert meta["user_local_time"] == "Mon 10:00"


def test_build_envelope_metadata_empty() -> None:
    assert mod._build_envelope_metadata({}) == {}


def test_build_envelope_metadata_skips_missing_fields() -> None:
    meta = mod._build_envelope_metadata({"conversation_id": 5})
    assert "chatbot_id" not in meta
    assert "user_local_time" not in meta


# ---------------------------------------------------------------------------
# _resolve_doc_path / _resolve_rag_metadata
# ---------------------------------------------------------------------------


def test_resolve_doc_path_returns_none_when_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mod, "_DOCUMENTS_ROOT", tmp_path)
    assert mod._resolve_doc_path(tmp_path / "nope.txt") is None


def test_resolve_doc_path_absolute_inside_root(tmp_path, monkeypatch) -> None:
    """An existing absolute path inside the root resolves directly."""
    monkeypatch.setattr(mod, "_DOCUMENTS_ROOT", tmp_path)
    target = tmp_path / "abs.txt"
    target.write_text("x", encoding="utf-8")
    assert mod._resolve_doc_path(target) == target


def test_resolve_doc_path_rglob_basename(tmp_path, monkeypatch) -> None:
    """A bare filename resolves via recursive search under the root."""
    monkeypatch.setattr(mod, "_DOCUMENTS_ROOT", tmp_path)
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    target = nested / "deep.txt"
    target.write_text("x", encoding="utf-8")
    # Pass only the basename; rglob finds it.
    assert mod._resolve_doc_path(tmp_path / "deep.txt") == target


def test_resolve_doc_path_candidate_inside_root(tmp_path, monkeypatch) -> None:
    """A relative path resolves via the (_DOCUMENTS_ROOT / path) join.

    The absolute resolve (branch 1) fails because the file doesn't
    exist relative to CWD; the candidate join (line 29-30) succeeds
    because the file exists under _DOCUMENTS_ROOT.
    """
    monkeypatch.setattr(mod, "_DOCUMENTS_ROOT", tmp_path)
    target = tmp_path / "cand.txt"
    target.write_text("x", encoding="utf-8")
    # Passing a RELATIVE path: branch 1 (file_path.resolve()) misses,
    # branch 2 ((_DOCUMENTS_ROOT / file_path).resolve()) hits.
    resolved = mod._resolve_doc_path(Path("cand.txt"))
    assert resolved == target


def test_resolve_doc_path_rglob_skips_outside_symlink(tmp_path, monkeypatch) -> None:
    """A symlink resolving outside root is skipped by the rglob loop.

    Covers the ``34->33`` loop-continue branch: a match whose resolve()
    is outside _DOCUMENTS_ROOT is skipped, and exhaustion returns None.
    """
    monkeypatch.setattr(mod, "_DOCUMENTS_ROOT", tmp_path)
    outside = tmp_path.parent / "outside_target.txt"
    outside.write_text("x", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "link_target.txt").symlink_to(outside)
    # Only match is the symlink; it resolves outside the root → skipped.
    assert mod._resolve_doc_path(tmp_path / "link_target.txt") is None


def test_resolve_rag_metadata_empty_ids() -> None:
    meta = mod._resolve_rag_metadata([])
    assert meta["is_rag_active"] is False


def test_resolve_rag_metadata_with_docs(tmp_path, monkeypatch) -> None:
    doc_path = tmp_path / "note.txt"
    doc_path.write_text("x", encoding="utf-8")
    monkeypatch.setattr(mod, "_DOCUMENTS_ROOT", tmp_path)

    fake_doc = SimpleNamespace(id=1, path=str(doc_path), active=True)
    fake_query = MagicMock()
    fake_query.filter.return_value = fake_query
    fake_query.all.return_value = [fake_doc]

    with patch(
        "airunner_services.database.models.document.Document"
    ) as doc_cls:
        # The lazy import inside _resolve_rag_metadata resolves to this
        # mock.  Document.id.in_(...) must be a callable, not an int.
        doc_cls.objects.query.return_value = fake_query
        meta = mod._resolve_rag_metadata([1])

    assert meta["is_rag_active"] is True
    assert meta["active_document_names"] == ["note.txt"]


def test_resolve_rag_metadata_exception_returns_empty(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mod, "_DOCUMENTS_ROOT", tmp_path)

    class _Boom:
        objects = None

    with patch(
        "airunner_services.database.models.document.Document", _Boom
    ):
        meta = mod._resolve_rag_metadata([1])
    assert meta["is_rag_active"] is False


# ---------------------------------------------------------------------------
# _persist_rag_to_conversation and append helpers
# ---------------------------------------------------------------------------


def test_persist_rag_no_conversation_id() -> None:
    mod._persist_rag_to_conversation(0, "m", {"is_rag_active": False})


def test_persist_rag_full_flow() -> None:
    """A valid conversation gets the RAG metadata + system message."""
    conv = SimpleNamespace(value=None, user_data=None)
    tx = MagicMock()
    tx.query.return_value = tx
    tx.filter.return_value = tx  # query().filter(...) chains back to tx
    tx.first.return_value = conv

    fake_objects = MagicMock()
    fake_objects.transaction.return_value.__enter__.return_value = tx
    fake_objects.transaction.return_value.__exit__.return_value = None

    # The lazy import resolves Conversation; .id is read by
    # _get_conversation_by_id via Conversation.id == conversation_id.
    with patch(
        "airunner_services.database.models.conversation.Conversation",
        SimpleNamespace(objects=fake_objects, id=MagicMock()),
    ):
        mod._persist_rag_to_conversation(
            5, "model-z", {"is_rag_active": True}, {"content": "sys note"}
        )

    assert conv.value is not None
    assert conv.value[0]["role"] == "system"
    assert any(
        m.get("metadata_type") == "rag_injection" for m in conv.value
    )
    assert conv.user_data["_pending_model"] == "model-z"
    tx.add.assert_called_once_with(conv)


def test_persist_rag_no_conversation_row() -> None:
    """A missing conversation row is a silent no-op."""
    tx = MagicMock()
    tx.query.return_value = tx
    tx.filter.return_value = tx
    tx.first.return_value = None

    fake_objects = MagicMock()
    fake_objects.transaction.return_value.__enter__.return_value = tx
    fake_objects.transaction.return_value.__exit__.return_value = None

    with patch(
        "airunner_services.database.models.conversation.Conversation",
        SimpleNamespace(objects=fake_objects, id=MagicMock()),
    ):
        mod._persist_rag_to_conversation(5, "m", {"is_rag_active": True})

    tx.add.assert_not_called()


def test_persist_rag_no_system_message() -> None:
    """Persisting without a rag_system_message skips the system entry.

    Covers the ``if not rag_system_message: return`` branch in
    _append_rag_system_message.
    """
    conv = SimpleNamespace(value=None, user_data=None)
    tx = MagicMock()
    tx.query.return_value = tx
    tx.filter.return_value = tx
    tx.first.return_value = conv

    fake_objects = MagicMock()
    fake_objects.transaction.return_value.__enter__.return_value = tx
    fake_objects.transaction.return_value.__exit__.return_value = None

    with patch(
        "airunner_services.database.models.conversation.Conversation",
        SimpleNamespace(objects=fake_objects, id=MagicMock()),
    ):
        # No rag_system_message argument → defaults to None.
        mod._persist_rag_to_conversation(5, "m", {"is_rag_active": True})

    assert conv.value is not None
    assert all(m.get("role") != "system" for m in conv.value)
    assert any(m.get("metadata_type") == "rag_injection" for m in conv.value)


def test_persist_rag_exception_is_silent() -> None:
    """A DB failure during persist is swallowed."""
    with patch(
        "airunner_services.database.models.conversation.Conversation",
        SimpleNamespace(objects=None),  # .transaction raises AttributeError
    ):
        mod._persist_rag_to_conversation(5, "m", {})
    # No raise.


def test_append_rag_system_message_dedup() -> None:
    value = [
        {"role": "system", "content": "same"},
        {"role": "user", "content": "hi"},
    ]
    mod._append_rag_system_message(
        value, {"role": "system", "content": "same"}, "now"
    )
    assert sum(1 for m in value if m.get("role") == "system") == 1


def test_append_rag_system_message_appends_new() -> None:
    value = []
    mod._append_rag_system_message(
        value, {"content": "new"}, "now"
    )
    assert value[-1] == {"role": "system", "content": "new", "timestamp": "now"}


def test_append_rag_metadata() -> None:
    value = []
    mod._append_rag_metadata(value, "model-x", {"is_rag_active": True}, "now")
    assert value[0]["metadata_type"] == "rag_injection"
    assert value[0]["model_version"] == "model-x"
    assert value[0]["is_rag_active"] is True


def test_append_rag_metadata_unknown_model() -> None:
    value = []
    mod._append_rag_metadata(value, None, {}, "now")
    assert value[0]["model_version"] == "unknown"


def test_store_pending_document_meta() -> None:
    conv = SimpleNamespace(user_data=None)
    mod._store_pending_document_meta(
        conv, "model-y", {"active_document_names": ["a.txt"]}
    )
    assert conv.user_data["_pending_model"] == "model-y"
    assert conv.user_data["_pending_active_documents"] == ["a.txt"]
