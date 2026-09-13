"""Single-call tool dedup and usage tracking for ToolExecutionMixin."""

from __future__ import annotations


class ToolExecutionDedupMixin:
    """Intercept duplicate single-call tools and track usage."""

    def _record_tool_usage(self, tool_calls: list[dict]) -> None:
        """Update ``_tool_last_used`` timestamps for cross-turn LRU cap.

        Called after every tool-execution cycle so that tools actually
        invoked by the model get their last-used turn bumped.  The
        ``_tool_last_used`` dict and ``_current_turn`` counter are
        initialized in ``_append_tools_with_cap`` (first call).
        """
        if not hasattr(self, "_tool_last_used"):
            return  # Appending hasn't run yet — nothing to record
        turn = getattr(self, "_current_turn", 0)
        if turn == 0:
            return
        for tc in tool_calls:
            name = tc.get("name", "")
            if name:
                self._tool_last_used[name] = turn

    # Tools that should be called at most once per turn.
    #
    # Side-effect / state-mutating tools that don't accumulate:
    #   update_mood, block_user, clear_conversation,
    #   clear_chat_history
    #
    # Pure getters that return the same value each call:
    #   get_current_datetime, get_current_date_context,
    #   get_conversation_summary, get_research_summary,
    #   get_image_model_info, list_available_tools
    #
    # NOTE: switch_tool_category is intentionally NOT in this set.
    # It is stripped only on *success* inside _rebind_for_category
    # (line ~480) so a failed call (typo, disabled category) can
    # be retried in the same turn.  See Issue 1 in the review.
    #
    # Multi-call tools (NOT in this set):
    #   record_knowledge, recall_knowledge, search_web, search_news,
    #   rag_search, recall_character_facts, record_character_fact, etc.
    _SINGLE_CALL_TOOLS: frozenset[str] = frozenset({
        # State mutators
        "update_mood",
        "block_user",
        "clear_conversation",
        "clear_chat_history",
        # Pure getters (same result each call)
        "get_current_datetime",
        "get_current_date_context",
        "get_conversation_summary",
        "get_research_summary",
        "get_image_model_info",
        "list_available_tools",
    })

    def _intercept_single_call_duplicates(
        self, tool_calls: list[dict],
    ) -> tuple[list[dict], dict[str, str]]:
        """Return (*filtered_calls*, *synthetic_results*) for duplicate
        single-call tools.

        Single-call tools (``_SINGLE_CALL_TOOLS``) that have already
        executed this turn are intercepted here instead of being passed
        to ``ToolNode``.  A synthetic ``ToolMessage`` is produced for
        each so the model still sees a result, but ``self._tools`` is
        **not mutated** — the tool stays in the bound array so the
        prompt-cache prefix remains stable.

        Multi-call tools (e.g. ``record_knowledge``, ``search_news``)
        pass through unchanged.

        Args:
            tool_calls: Tool-call dicts from the current AIMessage.

        Returns:
            (*filtered_calls*, *synthetic_results*) — *filtered_calls*
            has duplicates removed; *synthetic_results* maps call_id →
            result text for synthetic ``ToolMessage`` construction.
        """
        executed = set(self._executed_tools)
        single_call = executed & self._SINGLE_CALL_TOOLS
        if not single_call:
            return tool_calls, {}

        filtered: list[dict] = []
        synthetic: dict[str, str] = {}
        removed = 0
        for tc in tool_calls:
            name = tc.get("name", "")
            if name in single_call:
                removed += 1
                synthetic[tc["id"]] = (
                    f"Tool '{name}' was already executed earlier this "
                    f"turn and its result has not changed."
                )
            else:
                filtered.append(tc)

        if removed:
            self.logger.info(
                "Tool dedup: intercepted %d duplicate single-call "
                "tool(s) %s — replaced with synthetic ToolMessages "
                "(tools array unchanged at %d entries)",
                removed,
                sorted(single_call & {tc.get("name", "") for tc in tool_calls}),
                len(self._tools),
            )
        return filtered, synthetic
