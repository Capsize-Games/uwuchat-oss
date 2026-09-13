"""Tool result detail extraction for ToolExecutionMixin."""

from __future__ import annotations

import re


class ToolExecutionDetailsMixin:
    """Extract display details from tool call args and results."""

    def _extract_query_from_args(self, tool_args: dict) -> str:
        """Extract primary query/argument from tool arguments.

        Args:
            tool_args: Tool argument dictionary

        Returns:
            Extracted query string (truncated to 50 chars)
        """
        query = (
            tool_args.get("query")
            or tool_args.get("search_query")
            or tool_args.get("prompt")
            or str(tool_args)[:50]
        )
        return query

    def _find_matching_tool_call(
        self, tool_call_id: str, tool_calls: list
    ) -> dict | None:
        """Find tool call matching the given ID.

        Args:
            tool_call_id: Tool call ID to find
            tool_calls: List of tool call dictionaries

        Returns:
            Matching tool call dict or None
        """
        for tc in tool_calls:
            if tc.get("id") == tool_call_id:
                return tc
        return None

    def _extract_tool_details(
        self, tool_name: str, result_content: str
    ) -> str | None:
        """Extract relevant details from tool result for status display.

        Args:
            tool_name: Name of the tool that was executed
            result_content: The result content from the tool

        Returns:
            Brief details string for display (e.g., "foxnews.com, cnn.com").
            Code-mode tools (read_file, execute_command, list_files, ...)
            return a concise snippet of the actual result so the client
            shows what the tool returned instead of an empty bubble.
        """
        if tool_name == "search_web":
            return self._extract_web_search_details(result_content)
        elif tool_name == "rag_search":
            return self._extract_rag_search_details(result_content)
        # Code-mode proxy tools: surface a short, useful preview of the
        # actual result so the UI shows the tool response (the user's
        # "blank line / tool failed" symptom was empty details).
        if tool_name in {
            "read_file", "execute_command", "list_files", "run_tests",
            "codebase_search", "list_registered_projects",
            "write_to_file", "apply_diff", "search_replace", "edit_file",
        }:
            return self._summarize_result(result_content)
        return None

    @staticmethod
    def _summarize_result(result_content: str) -> str:
        """Return a concise one-line preview of a tool result."""
        text = str(result_content or "").strip()
        if not text:
            return "no output"
        one_line = " ".join(text.split())
        if len(one_line) <= 120:
            return one_line
        return one_line[:117] + "..."

    @staticmethod
    def _is_tool_error_result(result_content: str) -> bool:
        """Return True when a tool result content indicates failure.

        The code-mode proxy flattens the harness's ``{ok, isError,
        content}`` into a plain content string (see
        ``_proxy_helpers.call_tool``), so the only error signal
        available downstream is the content's text.  Recognizes the
        proxy's own error strings plus the harness's ``[Error]``
        prefix.  Non-code-mode tool results (search, etc.) that carry
        an "Error:" prefix are also surfaced as failures.
        """
        text = str(result_content or "").strip()
        if not text:
            return False
        lowered = text.lower()
        if lowered.startswith("error:"):
            return True
        if lowered.startswith("[error]"):
            return True
        if lowered.startswith("tool error:"):
            return True
        if lowered.startswith("<host-exec>") and " error" in lowered:
            return True
        return False

    def _extract_web_search_details(
        self, result_content: str
    ) -> str | None:
        """Extract domain names from web search results.

        Args:
            result_content: Web search result content

        Returns:
            Comma-separated domain names or None
        """
        urls = re.findall(r"URL: (https?://[^\s]+)", result_content)
        if urls:
            # Extract domain names only
            domains = [url.split("/")[2] for url in urls[:3]]  # Top 3
            return ", ".join(domains)
        return None

    def _extract_rag_search_details(self, result_content: str) -> str:
        """Extract details from RAG search results.

        Args:
            result_content: RAG search result content

        Returns:
            Status string ("no results" or "found results")
        """
        if "No results" in result_content or "couldn't find" in result_content:
            return "no results"
        else:
            return "found results"
