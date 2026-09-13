from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from airunner_services.ipc.messages import EnvelopeStatus, StreamDelta

try:
    from airunner_services.settings import AIRUNNER_BASE_PATH as _SETTINGS_BASE
except ImportError:  # pragma: no cover - import-time fallback only
    # Matches the documented AIRUNNER_BASE_PATH default (see
    # wiki/Deployment.md) rather than a shared, world-writable /tmp.
    _SETTINGS_BASE = str(Path.home() / ".local" / "share" / "airunner")
_DOCUMENTS_ROOT = Path(
    os.environ.get("AIRUNNER_DOCUMENTS_ROOT")
    or os.environ.get("AIRUNNER_BASE_PATH")
    or _SETTINGS_BASE
).resolve()


def _resolve_doc_path(file_path: Path) -> Path | None:
    """Resolve a document path within _DOCUMENTS_ROOT."""
    root = str(_DOCUMENTS_ROOT)
    resolved = file_path.resolve()
    if str(resolved).startswith(root) and resolved.exists():
        return resolved
    candidate = (_DOCUMENTS_ROOT / file_path).resolve()
    if str(candidate).startswith(root) and candidate.exists():
        return candidate
    basename = file_path.name
    matches = list(_DOCUMENTS_ROOT.rglob(basename))
    for match in matches:
        if str(match.resolve()).startswith(root):
            return match.resolve()
    return None


def _resolve_rag_metadata(active_doc_ids: list[int]) -> dict[str, Any]:
    """Resolve names of the attached documents for the flow inspector."""
    empty_meta: dict[str, Any] = {
        "is_rag_active": False,
        "active_document_ids": [],
        "active_document_names": [],
        "rag_text_preview": "",
    }
    if not active_doc_ids:
        return empty_meta
    logging = __import__("logging").getLogger(__name__)
    try:
        from airunner_services.database.models.document import Document

        doc_names: list[str] = []
        docs = (
            Document.objects.query()
            .filter(Document.id.in_(active_doc_ids))
            .filter(Document.active.is_(True))
            .all()
        )
        for doc in docs:
            resolved = _resolve_doc_path(Path(doc.path))
            doc_names.append(
                resolved.name if resolved else Path(doc.path).name
            )
        logging.info(
            "RAG: %d active document(s) attached for IDs %s",
            len(doc_names),
            active_doc_ids,
        )
        return {
            "is_rag_active": bool(doc_names),
            "active_document_ids": active_doc_ids,
            "active_document_names": doc_names,
            "rag_text_preview": "",
        }
    except Exception as exc:
        logging.error("RAG metadata resolution failed: %s", exc, exc_info=True)
        return empty_meta


def _persist_rag_to_conversation(
    conversation_id: int,
    model: str | None,
    rag_meta: dict[str, Any],
    rag_system_message: dict[str, Any] | None = None,
) -> None:
    """Persist RAG metadata AND the RAG system message to conversation."""
    if not conversation_id:
        return
    try:
        import datetime as _dt

        from airunner_services.database.models.conversation import Conversation

        with Conversation.objects.transaction() as tx:
            conv = _get_conversation_by_id(tx, conversation_id)
            if conv is None:
                return
            now = _dt.datetime.now(_dt.timezone.utc).isoformat()
            value = _ensure_list(conv.value)
            _append_rag_system_message(value, rag_system_message, now)
            _append_rag_metadata(value, model, rag_meta, now)
            _store_pending_document_meta(conv, model, rag_meta)
            conv.value = value
            tx.add(conv)
    except Exception:
        pass


def _get_conversation_by_id(tx, conversation_id: int):
    """Return a conversation row within a transaction, or None."""
    from airunner_services.database.models.conversation import Conversation

    return (
        tx.query(Conversation)
        .filter(Conversation.id == conversation_id)
        .first()
    )


def _ensure_list(value) -> list:
    """Return *value* as a list or an empty list."""
    return value if isinstance(value, list) else []


def _append_rag_system_message(
    value: list,
    rag_system_message: dict[str, Any] | None,
    now: str,
) -> None:
    """Append a RAG system message to *value* unless duplicate."""
    if not rag_system_message:
        return
    content = rag_system_message.get("content", "")
    already_stored = any(
        m.get("role") == "system" and m.get("content") == content
        for m in value[-3:]
    )
    if not already_stored:
        value.append({"role": "system", "content": content, "timestamp": now})


def _append_rag_metadata(
    value: list,
    model: str | None,
    rag_meta: dict[str, Any],
    now: str,
) -> None:
    """Append a rag_injection metadata entry."""
    value.append(
        {
            "metadata_type": "rag_injection",
            "model_version": model or "unknown",
            "timestamp": now,
            **rag_meta,
        }
    )


def _store_pending_document_meta(
    conv,
    model: str | None,
    rag_meta: dict[str, Any],
) -> None:
    """Store pending model + document info in conversation user_data."""
    active_doc_names = rag_meta.get("active_document_names", [])
    existing = conv.user_data or {}
    existing["_pending_model"] = model or "unknown"
    existing["_pending_active_documents"] = list(active_doc_names)
    conv.user_data = existing


def websocket_chunk(delta: StreamDelta) -> dict[str, Any]:
    """Convert a runtime stream delta into websocket payload shape."""
    if delta.status is EnvelopeStatus.FAILED:
        return {
            "type": "error",
            "content": delta.metadata.get("error", "LLM runtime failed"),
            "done": True,
        }
    msg_type = delta.metadata.get("message_type", "")
    if msg_type in ("tool_status", "mood"):
        return _websocket_tool_or_mood(delta, msg_type)
    if msg_type == "system":
        return {
            "type": "error",
            "error": delta.delta.get("content", ""),
            "done": delta.final,
        }
    payload: dict[str, Any] = {
        "type": msg_type if msg_type in ("thinking",) else "chunk",
        "content": delta.delta.get("content", ""),
        "done": delta.final,
    }
    tool_calls = delta.delta.get("tool_calls")
    if tool_calls:
        payload["tool_calls"] = tool_calls
    if delta.final:
        call_chain_id = delta.metadata.get("call_chain_id")
        if call_chain_id:
            payload["call_chain_id"] = call_chain_id
    return payload


def _websocket_tool_or_mood(
    delta: StreamDelta, msg_type: str
) -> dict[str, Any]:
    """Parse a tool_status or mood delta into a websocket payload."""
    import json as _json

    try:
        data = _json.loads(delta.delta.get("content", "{}"))
    except Exception:
        data = {}
    return {"type": msg_type, "done": False, **data}


def _parse_raw_messages(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract messages from a websocket payload (backward compat)."""
    raw = data.get("messages") or []
    if not raw:
        raw = [
            {
                "role": "user",
                "content": str(data.get("message", "")).strip(),
            }
        ]
    return raw


def _build_envelope_metadata(data: dict[str, Any]) -> dict[str, Any]:
    """Build runtime metadata from a websocket payload."""
    metadata: dict[str, Any] = {}
    profile = data.get("gguf_runtime_profile")
    if profile:
        metadata["gguf_runtime_profile"] = profile
    conversation_id = data.get("conversation_id")
    if conversation_id is not None:
        metadata["conversation_id"] = conversation_id
    chatbot_id = data.get("chatbot_id")
    if chatbot_id is not None:
        metadata["chatbot_id"] = chatbot_id
    user_local_time = data.get("user_local_time")
    if user_local_time:
        metadata["user_local_time"] = user_local_time
    return metadata
