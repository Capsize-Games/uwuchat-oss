"""Core lifecycle and deferred tool loading for ToolExecutionMixin."""

from __future__ import annotations

from typing import Optional

from airunner_services.llm.managers.forced_tool_execution_policy import (
    ForcedToolExecutionPolicy,
)
from airunner_services.settings import AIRUNNER_LOG_LEVEL
from airunner_services.utils.application import get_logger


class ToolExecutionCoreMixin:
    """Initialize tool execution state and load deferred tools."""

    def __init__(self):
        """Initialize tool execution mixin."""
        super().__init__()
        self.logger = get_logger(__name__, AIRUNNER_LOG_LEVEL)
        self._tools = []
        self._conversation_id: Optional[int] = None
        self._executed_tools: list[str] = (
            []
        )  # Track tools called in current invocation
        # Tool names legitimately discovered via search_tools this turn.
        # Populated when search_tools returns results; gated in
        # _ensure_tools_loaded so deferred tools are only auto-loaded
        # when actually discovered.
        self._discovered_tools: set[str] = set()
        # switch_tool_category call IDs already handled by the early
        # prebind so _handle_category_switch can skip the duplicate.
        self._prebound_switch_ids: set[str] = set()

    def _get_forced_tool_policy(self) -> ForcedToolExecutionPolicy:
        """Return the cached forced-tool execution helper."""
        helper = getattr(self, "_forced_tool_policy", None)
        if helper is None:
            helper = ForcedToolExecutionPolicy(self)
            self._forced_tool_policy = helper
        return helper

    @staticmethod
    def _ensure_runtime_compat() -> None:
        """Inject missing ExecutionInfo / ServerInfo into langgraph.runtime.

        langgraph 1.0.10–1.1.0 ship prebuilt/tool_node.py that imports
        ``ExecutionInfo`` and ``ServerInfo`` from ``langgraph.runtime``,
        but ``runtime.py`` does not define them.  The same versions also
        access ``runtime.execution_info`` / ``runtime.server_info`` on
        ``Runtime`` instances, but ``Runtime`` (a frozen+slots dataclass)
        lacks those fields.  This shim adds stub classes **and** injects
        class-level defaults on ``Runtime`` so both the import and the
        runtime attribute access succeed.
        """
        import importlib
        import sys

        runtime_mod = sys.modules.get("langgraph.runtime")
        if runtime_mod is None:
            runtime_mod = importlib.import_module("langgraph.runtime")

        # --- Module-level stubs for ``from langgraph.runtime import …`` ---
        if not hasattr(runtime_mod, "ExecutionInfo"):

            class ExecutionInfo:
                """Stub for langgraph.runtime.ExecutionInfo."""

            runtime_mod.ExecutionInfo = ExecutionInfo

        if not hasattr(runtime_mod, "ServerInfo"):

            class ServerInfo:
                """Stub for langgraph.runtime.ServerInfo."""

            runtime_mod.ServerInfo = ServerInfo

        # --- Class-level defaults on Runtime (frozen+slots dataclass) ---
        runtime_cls = getattr(runtime_mod, "Runtime", None)
        if runtime_cls is not None:
            if not hasattr(runtime_cls, "execution_info"):
                runtime_cls.execution_info = None
            if not hasattr(runtime_cls, "server_info"):
                runtime_cls.server_info = None

    def _ensure_tools_loaded(
        self, tool_calls: list, state: dict | None = None,
    ) -> None:
        """Dynamically load deferred tools that were discovered via
        ``search_tools`` but are not yet in ``self._tools``.

        The ``search_tools`` meta-tool returns schemas for deferred tools
        so the LLM can discover them.  When the LLM subsequently calls one
        of those tools, the ToolNode must have the corresponding function
        available.  This method loads any missing tool from
        ``ToolRegistry`` and wraps it as a ``StructuredTool`` so that
        LangGraph can execute it.

        Only loads tools whose name appears in ``self._discovered_tools``
        (populated when ``search_tools`` actually executed and returned a
        schema).  Tools the model hallucinates or copies from conversation
        history without a real ``search_tools`` call are silently dropped
        instead of being loaded and executed.

        Args:
            tool_calls: List of tool-call dicts from the current
                AIMessage.
            state: Current workflow state (for discovering new tool names
                from search_tools results).
        """
        existing = {
            getattr(t, "name", getattr(t, "__name__", None))
            for t in self._tools
        }
        requested = {tc.get("name", "") for tc in tool_calls if tc.get("name")}
        missing = requested - existing - {None, ""}
        if not missing:
            return

        from airunner_services.llm.core.tool_registry import ToolRegistry
        from langchain_core.tools import StructuredTool

        discovered = self._discovered_tools
        for name in sorted(missing):
            if name not in discovered:
                self.logger.warning(
                    "Rejecting tool %r — not in discovered set "
                    "(search_tools was never called for it)",
                    name,
                )
                continue
            tool_info = ToolRegistry.get(name)
            if tool_info is None:
                self.logger.warning(
                    "Tool '%s' not found in registry — cannot execute", name
                )
                continue
            try:
                structured_tool = StructuredTool.from_function(
                    func=tool_info.func,
                    name=tool_info.name,
                    description=tool_info.description,
                    return_direct=tool_info.return_direct,
                )
                self._tools.append(structured_tool)
                self.logger.info(
                    "Discovered tool appended: %s (%d total tools)",
                    name,
                    len(self._tools),
                )
            except Exception:
                self.logger.exception(
                    "Failed to wrap deferred tool: %s", name
                )

        # Rebind after appending so newly-discovered tools are
        # available on the next model turn.  The append-only approach
        # preserves prior bindings (tools render first in Anthropic's
        # request format, so keeping the prefix stable is critical for
        # prompt caching).
        if missing:
            self._bind_tools_to_model()

    def _get_next_workflow_tool(self, _current_tool: str) -> str | None:
        """Get the next required tool in the coding workflow sequence.

        Previously enforced strict tool ordering, but this caused issues when
        workflows were already active or the model correctly chose to skip steps.

        Now returns None to allow the model to choose tools freely based on
        the workflow instructions in the system prompt.

        Args:
            current_tool: The tool that just executed

        Returns:
            None - workflow tool ordering is no longer enforced
        """
        # No longer enforce tool ordering - let the model follow instructions
        # The workflow state and instructions guide it appropriately
        return None
