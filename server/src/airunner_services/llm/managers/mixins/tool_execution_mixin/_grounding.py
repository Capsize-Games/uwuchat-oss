"""Grounding source capture for ToolExecutionMixin."""

from __future__ import annotations


class ToolExecutionGroundingMixin:
    """Capture search-tool results for the check_grounding tool."""

    # Tools whose results should be captured as grounding sources
    # for the check_grounding tool.  Mirrors
    # forced_tool_execution_policy._GROUNDING_FORCED_TOOLS.
    _GROUNDING_SOURCE_TOOLS: frozenset[str] = frozenset({
        "get_topic_brief",
        "search_news",
        "scrape_website",
        "search_fastsearch",
        "search_fastsearch_news",
        "search_web",
        "get_daily_newspaper",
    })

    def _stash_grounding_sources(
        self,
        tool_calls: list[dict],
        result_state: dict,
    ) -> None:
        """Capture SEARCH tool results for check_grounding to use later.

        Reads ToolMessage entries just added to result_state and stashes
        their content into both the grounding ContextVar (for immediate
        access within the same graph step) and the graph state dict (so
        it survives across any context boundaries between graph nodes).
        The tools node refreshes the ContextVar from state before every
        ToolNode.invoke() so check_grounding always sees the accumulated
        sources.
        """
        executed_names = {
            tc.get("name", "") for tc in tool_calls
        }
        if not executed_names & self._GROUNDING_SOURCE_TOOLS:
            return
        from airunner_services.llm.tools.grounding_tools_helpers import (
            add_grounding_source,
        )
        result_msgs = result_state.get("messages", [])
        accumulated: list[str] = list(
            result_state.get("grounding_sources", [])
        )
        for msg in reversed(result_msgs):
            if not hasattr(msg, "name"):
                continue
            if msg.name not in executed_names:
                continue
            content = (
                str(msg.content) if hasattr(msg, "content") else ""
            )
            if not content:
                continue
            text = self._extract_grounding_text(content)
            if text:
                add_grounding_source(text)
                accumulated.append(text)
        if accumulated != result_state.get("grounding_sources", []):
            result_state["grounding_sources"] = accumulated

    def _refresh_grounding_cache_from_state(
        self, state: dict,
    ) -> None:
        """Copy grounding sources from graph state into the ContextVar.

        Called before every ToolNode.invoke() so that check_grounding
        (which reads the ContextVar) sees sources accumulated by prior
        graph steps, even if the execution model crosses a context
        boundary between steps.
        """
        from airunner_services.llm.tools.grounding_tools_helpers import (
            clear_grounding_sources,
            add_grounding_source,
        )

        sources: list[str] = state.get("grounding_sources", [])
        if not sources:
            return
        clear_grounding_sources()
        for text in sources:
            add_grounding_source(text)

    @staticmethod
    def _extract_grounding_text(tool_result: str) -> str:
        """Extract the plain-text body from a tool result.

        Some tools return JSON like {"summary": "...", "results": [...]};
        prefer the summary field when present.

        When the JSON is truncated (e.g. cut at 4000 chars), the
        serialized string may not parse as valid JSON.  Try
        regex-extracting the ``"summary"`` value before falling back
        to using the raw text verbatim.
        """
        import json as _json
        import re

        stripped = tool_result.strip()
        if not stripped:
            return ""
        if not stripped.startswith("{"):
            return stripped

        # Path 1: valid JSON — prefer the "summary" field.
        try:
            parsed = _json.loads(stripped)
            if isinstance(parsed, dict):
                summary = parsed.get("summary", "")
                if summary:
                    return str(summary)
        except (_json.JSONDecodeError, TypeError):
            pass

        # Path 2: truncated/invalid JSON — try regex for "summary".
        match = re.search(
            r'"summary"\s*:\s*"((?:[^"\\]|\\.)*)"',
            stripped,
        )
        if match:
            value = match.group(1)
            if value:
                return value

        # Path 3: unrecoverable — return raw text.
        return stripped
