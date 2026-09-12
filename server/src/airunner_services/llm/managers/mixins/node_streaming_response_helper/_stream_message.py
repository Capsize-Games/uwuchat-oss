"""Final message construction and truncation checks.

``NodeStreamingMessageMixin`` assembles the final ``AIMessage`` from
streamed content and logs truncation diagnostics.  The module-level
helpers build the per-iteration labels used by the token-usage
recorder and the Inspect/Flow-Detail panel.
"""

from __future__ import annotations

from typing import Optional

from langchain_core.messages import AIMessage

from airunner_services.llm.managers.mixins.node_streaming_response_helper._base import (
    _dedupe_finish_reason,
)


def _extract_tool_names(tool_calls) -> list[str] | None:
    """Return the ordered list of tool names from *tool_calls*, or None."""
    if not tool_calls:
        return None
    names: list[str] = []
    for tc in tool_calls:
        name = tc.get("name", "") if isinstance(tc, dict) else ""
        if name:
            names.append(name)
    return names or None


def _iteration_label(state, tool_calls, phase: str = "DIALOGUE") -> str:
    """Return a descriptive label for one iteration."""
    node = "RESPONSE" if phase == "RESPONSE" else "DIALOGUE"
    if tool_calls:
        return f"{node} (tool call)"
    if state.streamed_content:
        return f"{node} (response)"
    return node


def _extract_prompt_text(prompt) -> str | None:
    """Return the full text of the SYSTEM message from *prompt*, or None."""
    if prompt is None:
        return None
    text = ""
    if isinstance(prompt, list):
        for msg in prompt:
            role = getattr(msg, "type", None) or ""
            if role == "system":
                content = str(getattr(msg, "content", "") or "")
                text = content
                break
        if not text:
            for msg in prompt:
                content = str(getattr(msg, "content", "") or "")
                if content.strip():
                    text = content
                    break
    else:
        text = str(prompt)
    return text if text else None


class NodeStreamingMessageMixin:
    """Build the final streamed message and truncation diagnostics."""

    def _build_streamed_message(self, state, prompt=None) -> AIMessage:
        """Build the final AIMessage from streamed content."""
        thinking_to_save = self._thinking_helper.thinking_to_save(state)
        tool_calls = None
        if state.accumulated_message is not None:
            tool_calls = getattr(
                state.accumulated_message, "tool_calls", None
            ) or None
        if not tool_calls:
            tool_calls = state.collected_tool_calls or None
        msg = self._owner._get_response_generation_helper().create_streamed_message(
            state.streamed_content,
            state.last_chunk_message,
            tool_calls,
            thinking_to_save,
        )
        phase = getattr(self._owner, "_current_node_phase", "DIALOGUE")
        label = _iteration_label(state, tool_calls, phase)
        prompt_preview = _extract_prompt_text(prompt)
        tool_names = _extract_tool_names(tool_calls)
        self._record_stream_usage(
            state, label, prompt_preview, phase,
            tool_names=tool_names,
        )
        self._check_truncation(state.accumulated_message, label)
        return msg

    def _check_truncation(
        self,
        msg: Optional[AIMessage],
        label: str,
    ) -> None:
        """Log when generation was silently truncated by max_tokens.

        OpenAI-compatible APIs return ``finish_reason: "length"`` when
        generation was cut off by the ``max_tokens`` budget (versus
        ``"stop"`` for natural completion).  Surfacing this as a log
        line makes future truncation diagnosable without requiring a
        user to notice a cut-off sentence.
        """
        if msg is None:
            return
        metadata = getattr(msg, "response_metadata", None) or {}
        finish_reason = _dedupe_finish_reason(
            metadata.get("finish_reason", "")
        )
        usage_meta = getattr(msg, "usage_metadata", None) or {}
        completion_tokens = (
            usage_meta.get("output_tokens")
            or usage_meta.get("completion_tokens")
            or 0
        )
        requested = getattr(self, "_active_max_tokens", None)
        self._owner.logger.info(
            "[TOKEN-DIAG] %s finish_reason=%r "
            "completion_tokens=%d max_tokens=%s",
            label,
            finish_reason,
            completion_tokens,
            requested if requested else "default",
        )
        if finish_reason == "length":
            self._owner.logger.warning(
                f"[TRUNCATION] {label} generation cut off by "
                f"max_tokens (finish_reason={finish_reason!r}, "
                f"completion_tokens={completion_tokens})"
            )
        elif finish_reason:
            self._owner.logger.debug(
                f"[TRUNCATION] {label} finished naturally "
                f"(finish_reason={finish_reason!r})"
            )

    def _fallback_empty_message(self) -> AIMessage:
        """Emit a fallback AIMessage when no chunks were generated."""
        self._owner.logger.error(
            "No generation chunks were returned; emitting fallback"
        )
        fallback_text = "We are experiencing an outage, please try again later."
        if self._owner._token_callback:
            try:
                self._owner._token_callback(fallback_text)
            except Exception:
                pass
        return AIMessage(
            content=fallback_text,
            additional_kwargs={"error": "no_generation_chunks"},
            tool_calls=[],
        )
