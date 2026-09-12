"""Streaming classification responses with thinking support."""

from __future__ import annotations

from typing import Any, Optional, Tuple

from langchain_core.messages import HumanMessage

from airunner_services.llm.thinking_parser import (
    detect_thinking_close_tag,
    detect_thinking_open_tag,
)
from airunner_services.llm_workflow_events import (
    resolve_llm_workflow_event_sink,
)


class ToolClassificationStreamingMixin:
    """Stream classification responses, splitting thinking from text."""

    def _emit_classification_thinking_event(
        self,
        status: str,
        content: str,
        request_id: Optional[str],
    ) -> None:
        """Emit one live classification-thinking update."""
        event_sink = resolve_llm_workflow_event_sink(self)
        if not getattr(event_sink, "active", False):
            return
        event_sink.emit_thinking(
            {
                "status": status,
                "content": content,
                "request_id": request_id,
            }
        )

    def _append_classification_thinking(
        self,
        state: dict[str, Any],
        content: str,
        allow_thinking: bool,
        request_id: Optional[str],
    ) -> None:
        """Accumulate and optionally stream one classification delta."""
        if not content:
            return
        state["thinking_parts"].append(content)
        if not allow_thinking:
            return
        if not state["thinking_started"]:
            self._emit_classification_thinking_event(
                "started",
                "",
                request_id,
            )
            state["thinking_started"] = True
        self._emit_classification_thinking_event(
            "streaming",
            content,
            request_id,
        )

    def _finish_classification_thinking(
        self,
        state: dict[str, Any],
        allow_thinking: bool,
        request_id: Optional[str],
    ) -> None:
        """Finish one streamed classification-thinking block."""
        if not state["in_thinking_block"]:
            return
        state["in_thinking_block"] = False
        state["thinking_tag_format"] = ""
        if not allow_thinking or not state["thinking_started"]:
            return
        self._emit_classification_thinking_event(
            "completed",
            "".join(state["thinking_parts"]),
            request_id,
        )

    def _consume_classification_stream_text(
        self,
        state: dict[str, Any],
        text: str,
        allow_thinking: bool,
        request_id: Optional[str],
    ) -> None:
        """Split one streamed classification chunk into thinking and text."""
        remaining = text
        while remaining:
            if state["in_thinking_block"]:
                found_close, before_close, after_close = (
                    detect_thinking_close_tag(
                        remaining,
                        state["thinking_tag_format"],
                    )
                )
                if not found_close:
                    self._append_classification_thinking(
                        state,
                        remaining,
                        allow_thinking,
                        request_id,
                    )
                    return
                self._append_classification_thinking(
                    state,
                    before_close,
                    allow_thinking,
                    request_id,
                )
                self._finish_classification_thinking(
                    state,
                    allow_thinking,
                    request_id,
                )
                remaining = after_close
                continue

            found_open, tag_format, before_open, after_open = (
                detect_thinking_open_tag(remaining)
            )
            if not found_open:
                state["visible_parts"].append(remaining)
                return
            if before_open:
                state["visible_parts"].append(before_open)
            state["in_thinking_block"] = True
            state["thinking_tag_format"] = tag_format
            remaining = after_open

    def _stream_classification_response(
        self,
        chat_model: Any,
        classification_prompt: str,
        allow_thinking: bool,
    ) -> Tuple[Optional[str], str]:
        """Return streamed classification thinking and visible text."""
        request_id = getattr(self, "_current_request_id", None)
        state = {
            "in_thinking_block": False,
            "thinking_started": False,
            "thinking_tag_format": "",
            "thinking_parts": [],
            "visible_parts": [],
        }
        # ---- PII masking before LLM egress ----
        vault = getattr(self, "_pii_vault", None)
        if vault is not None:
            from airunner_services.llm.pii.masker import mask_text
            classification_prompt = mask_text(classification_prompt, vault)
        # ---- end PII ----
        for chunk in chat_model.stream(
            [HumanMessage(content=classification_prompt)]
        ):
            chunk_message = getattr(chunk, "message", chunk)
            text = getattr(chunk_message, "content", "") or ""
            additional_kwargs = (
                getattr(chunk_message, "additional_kwargs", {}) or {}
            )
            reasoning_delta = additional_kwargs.get(
                "thinking_content"
            ) or additional_kwargs.get("reasoning_content")
            self._append_classification_thinking(
                state,
                reasoning_delta or "",
                allow_thinking,
                request_id,
            )
            if text:
                self._consume_classification_stream_text(
                    state,
                    text,
                    allow_thinking,
                    request_id,
                )
        self._finish_classification_thinking(
            state,
            allow_thinking,
            request_id,
        )
        thinking_text = "".join(state["thinking_parts"]).strip() or None
        response_text = "".join(state["visible_parts"])
        if thinking_text or not response_text:
            return thinking_text, response_text
        return self._split_classification_response(response_text)
