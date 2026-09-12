"""Prompt-building mixin — assembles the full system prompt + history.

Extracted from node_prompt_assembly_helper.py to keep each file under
the 250-line limit.  Contains build_prompt and the message-merging /
context-injection helpers.  Prompt-caching logic lives in
node_prompt_cache_mixin.py.
"""

from __future__ import annotations

import os

from langchain_core.messages import (
    BaseMessage,
)

from airunner_services.llm.managers.mixins.last_exchange_helper import (
    last_exchange_block,
)
from airunner_services.llm.managers.mixins.node_prompt_cache_mixin import (
    NodePromptCacheMixin,
)


class NodePromptBuilderMixin(NodePromptCacheMixin):
    """Build the full system + history prompt for model calls.

    Inherits cache-breakpoint logic from NodePromptCacheMixin.
    """

    def build_prompt(self, trimmed_messages: list[BaseMessage]):
        """Build one prompt with system, tools, and post-tool guidance."""
        chat_model = getattr(self._owner, "_chat_model", None)
        if chat_model and getattr(chat_model, "is_vision_model", False):
            return self._build_vision_prompt(trimmed_messages)
        merged = self._merge_consecutive_humans(trimmed_messages)
        trimmed_messages = merged
        # The local Ollama daemon (Qwen3.5-9B) drops ``role: "tool"``
        # messages, so the model never sees its tool results and re-issues
        # the same call forever.  Render ToolMessages as readable user
        # prose for the Ollama-compatible path only (proven to work by
        # direct eval against the daemon); other providers keep native
        # tool-call messages.  This runs AFTER the post-tool instruction
        # block below (which must still see the ToolMessages to compute
        # CONTINUE WORKING / error guidance).

        topic_shifted = False
        from airunner_services.llm.managers.mixins.node_topic_shift import (
            detect_topic_shift,
            topic_shift_annotation,
        )
        rolling_block: str = ""
        rolling_summary = self._get_rolling_summary()
        if rolling_summary:
            keep = int(
                os.getenv("AIRUNNER_SESSION_KEEP_RECENT", "8")
            )
            if len(trimmed_messages) > keep:
                trimmed_messages = trimmed_messages[-keep:]
            topic_shifted = detect_topic_shift(trimmed_messages)
            if topic_shifted:
                rolling_block = (
                    "[Background — earlier topics, not necessarily "
                    f"relevant to current question]: {rolling_summary}"
                )
            else:
                rolling_block = (
                    f"[Earlier in this conversation]: {rolling_summary}"
                )

        per_turn = getattr(self._owner, "_per_turn_context", "") or ""

        if topic_shifted:
            chatbot = getattr(self._owner, "chatbot", None)
            is_system_bot = getattr(chatbot, "is_system_bot", False)
            note = topic_shift_annotation(is_system_bot)
            per_turn = f"{note}\n\n{per_turn}" if per_turn else note

        # Post-tool instructions must live in the per-turn block, not
        # the system prompt — they contain text derived from real-time
        # tool results and would bust the prompt cache on every call.
        post_tool = (
            self._owner._get_post_tool_instructions_helper()
            .get_post_tool_instruction_text(trimmed_messages)
        )
        if post_tool:
            per_turn = (
                f"{per_turn}\n\n{post_tool}" if per_turn else post_tool
            )

        knowledge_block = self._gather_knowledge_context(
            trimmed_messages
        )
        conversation_block = self._gather_conversation_context(
            len(trimmed_messages)
        )
        if rolling_block:
            if conversation_block:
                conversation_block = (
                    f"{rolling_block}\n\n{conversation_block}"
                )
            else:
                conversation_block = rolling_block

        last_exchange = last_exchange_block(trimmed_messages)
        if last_exchange:
            if conversation_block:
                conversation_block = (
                    f"{conversation_block}\n\n{last_exchange}"
                )
            else:
                conversation_block = last_exchange

        # Ollama daemon rewrite: render ToolMessages as readable prose
        # AND materialized AIMessage tool_calls back to Qwen JSON.  Runs
        # AFTER the post-tool instruction block (which already saw the
        # ToolMessages) but BEFORE the messages are injected into the
        # human turn, so the daemon receives results it can actually
        # consume.
        from airunner_services.llm.managers.mixins.ollama_tool_result_rewriter import (
            rewrite_tool_results_for_ollama,
            should_rewrite_tool_results,
        )

        if should_rewrite_tool_results(self._owner):
            trimmed_messages = rewrite_tool_results_for_ollama(
                trimmed_messages,
            )

        trimmed_messages = self._inject_context_into_human_turn(
            trimmed_messages,
            per_turn,
            knowledge_block,
            conversation_block,
        )

        if self._is_claude_model():
            return self._build_claude_prompt(trimmed_messages)
        return self._build_standard_prompt(trimmed_messages)
