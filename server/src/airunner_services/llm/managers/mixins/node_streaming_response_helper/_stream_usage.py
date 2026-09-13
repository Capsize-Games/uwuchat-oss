"""Token-usage recording for streamed responses.

``NodeStreamingUsageMixin`` records one usage row per streamed
response.  When the round requested multiple tool calls the total
cost is split proportionally into one row per tool call so the
Inspect/Flow-Detail panel can attribute cost to each individual call
rather than leaving later calls unbilled.
"""

from __future__ import annotations


class NodeStreamingUsageMixin:
    """Record token usage from the final streaming chunk."""

    def _record_stream_usage(
        self, state, label: str, prompt_preview: str | None = None,
        phase: str = "DIALOGUE",
        tool_names: list[str] | None = None,
    ) -> None:
        """Record token usage; swallow errors (metrics must not break
        the stream)."""
        try:
            self._record_stream_usage_or_raise(
                state, label, prompt_preview, phase, tool_names
            )
        except Exception:
            pass

    def _record_stream_usage_or_raise(
        self, state, label: str, prompt_preview: str | None,
        phase: str, tool_names: list[str] | None,
    ) -> None:
        """Record usage rows; propagate exceptions to the caller."""
        usage = getattr(state, "last_usage_metadata", None) or {}
        inp = int(usage.get("input_tokens", 0)
                  or usage.get("prompt_tokens", 0) or 0)
        out = int(usage.get("output_tokens", 0)
                  or usage.get("completion_tokens", 0) or 0)
        from airunner_services.llm.managers.mixins.generation_usage \
            import cache_read_tokens_from_usage
        cache_read = cache_read_tokens_from_usage(usage)
        from airunner_services.llm.active_call_chain import (
            get_active_call_chain,
        )
        self._owner.logger.info(
            "[RECORD_STREAM] inp=%s out=%s cache_read=%s "
            "call_chain=%s",
            inp,
            out,
            cache_read,
            getattr(self._owner, "_call_chain_id", None)
            or get_active_call_chain(),
        )
        if inp == 0 and out == 0:
            return
        self._emit_usage_rows(
            state, label, phase, tool_names,
            inp=inp, out=out, cache_read=cache_read,
            prompt_preview=prompt_preview,
        )

    def _emit_usage_rows(
        self, state, label: str, phase: str,
        tool_names: list[str] | None, *,
        inp: int, out: int, cache_read: int,
        prompt_preview: str | None,
    ) -> None:
        """Emit one usage row per tool call, or a single combined row."""
        from airunner_services.llm.pipeline_loader import (
            pipeline_config,
        )
        pipeline_key = "RESPONSE" if phase == "RESPONSE" else "DIALOGUE"
        cfg = pipeline_config(pipeline_key)
        chat_model = getattr(self._owner, "_chat_model", None)
        model_id = (
            getattr(chat_model, "model", None)
            or cfg.get("model", "")
        )
        chatbot = getattr(self._owner, "chatbot", None)
        resp = "".join(state.streamed_content) or None
        split_count = max(len(tool_names or []), 1)
        for idx in range(split_count):
            self._emit_one_usage_row(
                idx, split_count, tool_names, pipeline_key, label,
                model_id, chatbot, inp, out, cache_read,
                prompt_preview, resp,
            )

    def _usage_slice(
        self, idx: int, split_count: int,
        tool_names: list[str] | None, pipeline_key: str, label: str,
        inp: int, out: int, cache_read: int,
    ) -> tuple[str, int, int, int]:
        """Compute one tool's proportional slice of the round's usage."""
        sub_label = label
        sub_inp = inp // split_count
        sub_out = out // split_count
        sub_cache = cache_read // split_count
        if split_count > 1 and tool_names:
            sub_label = (
                f"{pipeline_key} ({tool_names[idx]})"
            )
        # Last slice carries any remainder from integer
        # division so totals sum up exactly.
        if idx == split_count - 1:
            sub_inp = inp - sub_inp * (split_count - 1)
            sub_out = out - sub_out * (split_count - 1)
            sub_cache = (
                cache_read
                - sub_cache * (split_count - 1)
            )
        return sub_label, sub_inp, sub_out, sub_cache

    def _emit_one_usage_row(
        self, idx: int, split_count: int,
        tool_names: list[str] | None, pipeline_key: str, label: str,
        model_id: str, chatbot, inp: int, out: int, cache_read: int,
        prompt_preview: str | None, resp: str | None,
    ) -> None:
        """Record one usage row plus its pipeline-call text."""
        sub_label, sub_inp, sub_out, sub_cache = self._usage_slice(
            idx, split_count, tool_names, pipeline_key, label,
            inp, out, cache_read,
        )
        from airunner_services.data.tenant import get_tenant_key
        from airunner_services.llm.token_usage import (
            record_pipeline_call_text,
            record_usage,
        )
        from airunner_services.llm.active_call_chain import (
            get_active_call_chain,
        )
        usage_id = record_usage(
            pipeline_key=sub_label,
            model_id=model_id,
            input_tokens=sub_inp,
            output_tokens=sub_out,
            cache_read_tokens=sub_cache,
            chatbot_id=getattr(chatbot, "id", None)
            if chatbot else None,
            call_chain_id=(
                getattr(self._owner, "_call_chain_id", None)
                or get_active_call_chain()
            ),
            tenant_key=get_tenant_key(),
            prompt_char_count=(
                len(prompt_preview)
                if prompt_preview else None
            ),
            response_char_count=len(resp) if resp else None,
        )
        record_pipeline_call_text(
            usage_id=usage_id,
            tenant_key=get_tenant_key(),
            prompt_text=prompt_preview,
            response_text=resp,
        )
