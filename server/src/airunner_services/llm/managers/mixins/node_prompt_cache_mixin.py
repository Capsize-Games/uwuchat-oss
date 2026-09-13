"""Claude/Anthropic prompt-cache helpers for multi-breakpoint caching.

Extracted from node_prompt_builder_mixin.py to keep each file under
the 250-line limit.  Contains the Claude and standard prompt-building
paths plus cache-prefix diagnostic logging.
"""

from __future__ import annotations

from typing import List

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder


# Anthropic prompt-caching allows at most 4 cache_control markers per
# request.  This mixin uses 2–3 on the SystemMessage (segments A/B/C)
# plus 1 on conversation history, fitting within the budget.
_MAX_CACHE_BREAKPOINTS = 4


class NodePromptCacheMixin:
    """Cache-aware prompt building for Claude vs standard models."""

    _owner: any

    # ── model detection ──────────────────────────────────────────

    def _is_claude_model(self) -> bool:
        """Return True when the active model is Anthropic/Claude."""
        chat_model = getattr(self._owner, "_chat_model", None)
        if not chat_model:
            return False
        name = (
            getattr(chat_model, "model", None)
            or getattr(chat_model, "model_name", None)
            or ""
        )
        return "claude" in name.lower() or "anthropic" in name.lower()

    # ── prompt builders ──────────────────────────────────────────

    def _build_claude_prompt(
        self, trimmed_messages: List[BaseMessage]
    ):
        """Build the prompt for Claude models with multi-breakpoint
        cache_control segments.

        Reads pre-computed PromptSegments from the workflow manager
        (stored by apply_workflow_request_setup, which used the real
        per-turn action).  This guarantees the same prompt content as
        the non-Claude path — only the caching/grouping differs.

        Adds a cache_control marker on the last pre-turn message in
        conversation history so Anthropic can cache the stable older
        portion of the history across consecutive calls in the same
        session.
        """
        segments = getattr(self._owner, "_prompt_segments", None)
        if segments is None:
            # Fallback: no segments stored (e.g. custom prompt path).
            # Build a single-segment message with one cache_control.
            escaped = self.escape_system_prompt()
            self._log_cache_prefix_hash(escaped)
            prompt = ChatPromptTemplate.from_messages([
                ("system", escaped),
                MessagesPlaceholder(variable_name="messages"),
            ])
            result = prompt.invoke({"messages": trimmed_messages})
            return self._inject_cache_control(result.to_messages())

        system_msg = self._build_segmented_system_msg(segments)
        self._log_cache_prefix_segments(segments)
        prompt = ChatPromptTemplate.from_messages([
            system_msg,
            MessagesPlaceholder(variable_name="messages"),
        ])
        result = prompt.invoke({"messages": trimmed_messages})
        # Add cache_control on the last pre-turn history message.
        msg_list = result.to_messages()
        return self._inject_history_cache_control(msg_list)

    def _build_standard_prompt(
        self, trimmed_messages: List[BaseMessage]
    ):
        """Build the prompt for non-Claude models (single cache block)."""
        escaped = self.escape_system_prompt()
        escaped = self.add_tool_instructions(escaped)
        self._log_cache_prefix_hash(escaped)
        prompt = ChatPromptTemplate.from_messages([
            ("system", escaped),
            MessagesPlaceholder(variable_name="messages"),
        ])
        result = prompt.invoke({"messages": trimmed_messages})
        return self._inject_cache_control(result.to_messages())

    # ── cache_control injection ──────────────────────────────────

    @staticmethod
    def _inject_cache_control(
        messages: List[BaseMessage],
    ) -> List[BaseMessage]:
        """Wrap the SystemMessage content in an ephemeral cache block.

        Used only by the standard (non-Claude) path and the Claude
        fallback path.  The main Claude path builds multi-breakpoint
        segments in `_build_segmented_system_msg`.
        """
        result = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                text = (
                    msg.content
                    if isinstance(msg.content, str)
                    else "".join(
                        b.get("text", "")
                        if isinstance(b, dict)
                        else str(b)
                        for b in msg.content
                    )
                )
                msg = SystemMessage(
                    content=[{
                        "type": "text",
                        "text": text,
                        "cache_control": {"type": "ephemeral"},
                    }]
                )
            result.append(msg)
        return result

    def _inject_history_cache_control(
        self, messages: List[BaseMessage],
    ) -> List[BaseMessage]:
        """Add a cache_control marker on the last pre-turn message.

        Finds the last HumanMessage (current turn start) and places
        ``cache_control: {"type": "ephemeral"}`` on the message
        immediately before it — this is the stable older history that
        does not change between consecutive calls in the same session.

        The system message already carries up to 3 cache_control
        markers (segments A/B/C), so this fourth marker brings the
        total to at most 4, matching Anthropic's documented limit.

        Also emits a diagnostic log line with the history-segment
        hash and length (never the content itself).
        """
        last_human_idx: int | None = None
        for i in range(len(messages) - 1, -1, -1):
            if isinstance(messages[i], HumanMessage):
                last_human_idx = i
                break

        if last_human_idx is None or last_human_idx < 1:
            return messages  # No pre-turn history to mark

        pre_turn_idx = last_human_idx - 1
        pre_msg = messages[pre_turn_idx]
        if isinstance(pre_msg, SystemMessage):
            return messages  # Already has cache_control

        # Build the cache_control-tagged content block.
        raw = pre_msg.content
        if isinstance(raw, str):
            text_content = raw
            tagged = [{
                "type": "text",
                "text": raw,
                "cache_control": {"type": "ephemeral"},
            }]
        elif isinstance(raw, list):
            text_content = "".join(
                b.get("text", "") if isinstance(b, dict) else str(b)
                for b in raw
            )
            tagged = list(raw)
            if tagged:
                tagged[-1] = {
                    **tagged[-1],
                    "cache_control": {"type": "ephemeral"},
                }
        else:
            text_content = str(raw)
            tagged = [{
                "type": "text",
                "text": str(raw),
                "cache_control": {"type": "ephemeral"},
            }]

        # Use model_copy to preserve all fields (id, response_metadata,
        # usage_metadata, tool_calls, tool_call_id, etc.) without a
        # hand-maintained attribute allowlist.  This also avoids the
        # ToolMessage constructor crash — ToolMessage requires
        # tool_call_id as a constructor arg.
        new_msg = pre_msg.model_copy(update={"content": tagged})

        result = list(messages)
        result[pre_turn_idx] = new_msg

        # Diagnostic: log history-segment hash and length.
        try:
            import hashlib

            hist_hash = hashlib.sha256(
                text_content.encode("utf-8")
            ).hexdigest()[:12]
            self._owner.logger.info(
                "[CACHE SEGMENTS] hist_hash=%s hist_len=%d "
                "hist_msg_type=%s",
                hist_hash,
                len(text_content),
                pre_msg.__class__.__name__,
            )
        except Exception:
            pass  # Logging is best-effort; never fail prompt build

        return result

    @staticmethod
    def _build_segmented_system_msg(segments) -> SystemMessage:
        """Return a SystemMessage whose content is a list of text
        blocks, each with its own ``cache_control`` marker, ordered
        A → B → C for maximum prefix reuse.

        Segment B and C are only included when non-empty; Segment A
        is always present.  Curly braces are escaped so that
        ChatPromptTemplate does not treat them as template variables.
        """
        blocks: list[dict] = []
        for raw_parts in (
            segments.segment_a,
            segments.segment_b,
            segments.segment_c,
        ):
            if not raw_parts:
                continue
            text = "\n\n".join(raw_parts)
            escaped = text.replace("{", "{{").replace("}", "}}")
            blocks.append({
                "type": "text",
                "text": escaped,
                "cache_control": {"type": "ephemeral"},
            })
        return SystemMessage(content=blocks)

    # ── diagnostic logging (hashes only, no content) ─────────────

    def _log_cache_prefix_hash(self, escaped_system_prompt: str) -> None:
        """Log hashes of the system prompt and bound tools, not content.

        Diagnostic only -- lets us confirm byte-identity of the
        Anthropic cache prefix (tools + system) across real calls
        without logging any actual prompt/tool content, per the
        project's logging policy.
        """
        try:
            import hashlib

            tools = getattr(self._owner, "_tools", None) or []
            tool_sig = "|".join(
                getattr(t, "name", getattr(t, "__name__", ""))
                for t in tools
            )
            sys_hash = hashlib.sha256(
                escaped_system_prompt.encode("utf-8")
            ).hexdigest()[:12]
            tools_hash = hashlib.sha256(
                tool_sig.encode("utf-8")
            ).hexdigest()[:12]
            self._owner.logger.info(
                "[CACHE PREFIX] system_hash=%s tools_hash=%s "
                "tool_count=%d system_len=%d",
                sys_hash,
                tools_hash,
                len(tools),
                len(escaped_system_prompt),
            )
        except Exception as exc:
            self._owner.logger.warning(
                "[CACHE PREFIX] hash logging failed: %s", exc,
                exc_info=True,
            )

    def _log_cache_prefix_segments(self, segments) -> None:
        """Log per-segment hashes for cache-breakpoint diagnostics.

        Emits one log line with segment_A_hash, segment_B_hash,
        segment_C_hash and their lengths, plus the tools hash.
        Tool content is never logged — hashes only, per policy.
        """
        try:
            import hashlib

            tools = getattr(self._owner, "_tools", None) or []
            tool_sig = "|".join(
                getattr(t, "name", getattr(t, "__name__", ""))
                for t in tools
            )
            tools_hash = hashlib.sha256(
                tool_sig.encode("utf-8")
            ).hexdigest()[:12]

            hashes: dict[str, str] = {}
            lengths: dict[str, int] = {}
            for label, raw_parts in (
                ("A", segments.segment_a),
                ("B", segments.segment_b),
                ("C", segments.segment_c),
            ):
                joined = "\n\n".join(raw_parts)
                lengths[label] = len(joined)
                hashes[label] = hashlib.sha256(
                    joined.encode("utf-8")
                ).hexdigest()[:12]

            self._owner.logger.info(
                "[CACHE SEGMENTS] "
                "segA_hash=%s segA_len=%d "
                "segB_hash=%s segB_len=%d "
                "segC_hash=%s segC_len=%d "
                "tools_hash=%s tool_count=%d",
                hashes["A"],
                lengths["A"],
                hashes["B"],
                lengths["B"],
                hashes["C"],
                lengths["C"],
                tools_hash,
                len(tools),
            )
        except Exception as exc:
            self._owner.logger.warning(
                "[CACHE SEGMENTS] hash logging failed: %s", exc,
                exc_info=True,
            )
