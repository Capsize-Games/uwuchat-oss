"""Conversation endpoint wrappers for GuiDaemonClient."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, Optional
from urllib.parse import urlencode

from airunner_services.contract_enums import LLMActionType
from airunner_services.llm.llm_request import LLMRequest


class GuiDaemonClientConversationEndpointsMixin:
    """Daemon LLM streaming and conversation endpoints."""

    def stream_llm_request(
        self,
        prompt: str,
        llm_request: LLMRequest,
        action: LLMActionType,
        request_id: str,
        *,
        search_hints: Optional[Dict[str, Any]] = None,
        conversation_id: Optional[int] = None,
        node_id: Optional[str] = None,
    ) -> Iterable[Dict[str, Any]]:
        """Yield NDJSON chunks from the daemon's legacy LLM endpoint."""
        headers = {"x-request-id": request_id}
        with self._request(
            "POST",
            "/llm/generate",
            json_payload=self._llm_payload(
                prompt,
                llm_request,
                action,
                search_hints=search_hints,
                conversation_id=conversation_id,
                node_id=node_id,
            ),
            headers=headers,
            stream=True,
        ) as response:
            for line in response.iter_lines(chunk_size=1):
                if not line:
                    continue
                yield json.loads(line.decode("utf-8"))

    def list_conversations(
        self,
        *,
        limit: int = 50,
        auto_start: bool = False,
    ) -> list[Dict[str, Any]]:
        """Return serialized conversation metadata from the daemon."""
        query = urlencode({"limit": limit})
        response = self._request(
            "GET",
            f"/api/v1/llm/conversations?{query}",
            auto_start=auto_start,
        )
        return list(response.json().get("conversations") or [])

    def get_conversation_session(
        self,
        *,
        conversation_id: Optional[int] = None,
        max_messages: int = 50,
        auto_start: bool = False,
    ) -> Dict[str, Any]:
        """Return one serialized conversation session from the daemon."""
        query = {"max_messages": max_messages}
        if conversation_id is not None:
            query["conversation_id"] = conversation_id
        response = self._request(
            "GET",
            f"/api/v1/llm/conversations/session?{urlencode(query)}",
            auto_start=auto_start,
        )
        return response.json()

    def select_conversation(
        self,
        conversation_id: int,
        *,
        max_messages: int = 50,
        auto_start: bool = False,
    ) -> Dict[str, Any]:
        """Select one daemon-side conversation and return the session payload."""
        response = self._request(
            "POST",
            "/api/v1/llm/conversations/select",
            json_payload={
                "conversation_id": conversation_id,
                "max_messages": max_messages,
            },
            auto_start=auto_start,
        )
        return response.json()

    def summarize_conversation(
        self,
        conversation_id: int,
        *,
        auto_start: bool = False,
    ) -> Dict[str, Any]:
        """Return one daemon-generated summary payload for a conversation."""
        response = self._request(
            "GET",
            f"/api/v1/llm/conversations/{conversation_id}/summary",
            auto_start=auto_start,
        )
        return response.json()

    def delete_conversation(
        self,
        conversation_id: int,
        *,
        auto_start: bool = False,
    ) -> Dict[str, Any]:
        """Delete one conversation through the daemon conversation API."""
        response = self._request(
            "DELETE",
            f"/api/v1/llm/conversations/{conversation_id}",
            auto_start=auto_start,
        )
        return response.json()
