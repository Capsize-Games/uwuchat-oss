"""Custom tool compilation for ToolManager — exec() sandboxed compilation."""

from __future__ import annotations

import logging
import time
from concurrent.futures import (
    ThreadPoolExecutor,
    TimeoutError as FuturesTimeoutError,
)
from typing import Any, Callable, Optional

_security_audit_logger = logging.getLogger("airunner.security.custom_tools")

CUSTOM_TOOL_EXEC_TIMEOUT_SECONDS = 10


class ToolManagerCustomMixin:
    """Custom tool compilation and loading for ToolManager."""

    logger: Any
    _get_tool_by_name: Any
    _wrap_tool_with_dependencies: Any

    def _load_custom_tools(self) -> list[Callable]:
        """Load custom tools created by the agent from the database."""
        try:
            from airunner_services.database.models.llm_tool import LLMTool

            enabled_tools = LLMTool.objects.filter_by(enabled=True) or []
            results = []
            for tool_record in enabled_tools:
                try:
                    if not getattr(tool_record, "safety_validated", False):
                        self.logger.warning(
                            "Skipping custom tool '%s': safety_validated "
                            "false",
                            tool_record.name,
                        )
                        continue
                    func = self._compile_custom_tool(tool_record)
                    if func:
                        results.append(func)
                except Exception as error:
                    self.logger.error(
                        "Error loading custom tool '%s': %s",
                        tool_record.name,
                        error,
                    )
            return results
        except Exception as error:
            self.logger.error("Error loading custom tools: %s", error)
            return []

    def _compile_custom_tool(self, tool_record) -> Optional[Callable]:
        """Compile one custom tool from its database record via exec()."""
        try:
            from langchain_core.tools import tool
            from airunner_services.llm.core.code_sandbox import (
                create_safe_builtins,
            )

            namespace = {
                "tool": tool,
                "__name__": f"custom_tool_{tool_record.name}",
                "__builtins__": create_safe_builtins(),
            }
            self._exec_custom_code(tool_record.code, namespace)
            return self._find_and_wrap_tool(namespace, tool_record)
        except Exception as error:
            self.logger.error(
                "Error compiling tool '%s': %s",
                tool_record.name,
                error,
            )
            return None

    def _exec_custom_code(self, code: str, namespace: dict) -> None:
        """Execute custom code in a sandboxed thread with timeout.

        AST-based validation runs *before* ``exec()``, at compilation
        time, on every load — not just when the tool is first saved.
        This closes the gap where a tool with ``safety_validated=True``
        was later modified in the database without re-validation.
        """
        from airunner_services.llm.core.code_sandbox_ast import (
            validate_code_safety_ast,
        )

        ok, reason = validate_code_safety_ast(code)
        if not ok:
            _security_audit_logger.warning(
                "custom_tool_rejected reason=%s code_len=%d",
                reason, len(code),
            )
            raise ValueError(f"Unsafe custom tool code: {reason}")

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(exec, code, namespace)
            try:
                future.result(timeout=CUSTOM_TOOL_EXEC_TIMEOUT_SECONDS)
            except FuturesTimeoutError:
                raise RuntimeError(
                    f"Custom tool compilation timed out after "
                    f"{CUSTOM_TOOL_EXEC_TIMEOUT_SECONDS}s"
                )

    def _find_and_wrap_tool(
        self,
        namespace: dict,
        tool_record,
    ) -> Optional[Callable]:
        """Find the compiled tool in namespace and wrap with tracking."""
        for item in namespace.values():
            if not (callable(item) and hasattr(item, "name")):
                continue
            return self._make_tracked_tool(item, tool_record)
        return None

    def _make_tracked_tool(
        self,
        original_func: Callable,
        tool_record,
    ) -> Callable:
        """Wrap one tool function with audit logging and timeout."""

        def tracked_tool(*args, _func=original_func, **kwargs):
            _security_audit_logger.info(
                "custom_tool_invoked tool=%s ts=%s",
                tool_record.name,
                time.time(),
            )
            with ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(_func, *args, **kwargs)
                try:
                    result = fut.result(
                        timeout=CUSTOM_TOOL_EXEC_TIMEOUT_SECONDS,
                    )
                    tool_record.increment_usage(success=True)
                    return result
                except FuturesTimeoutError:
                    tool_record.increment_usage(
                        success=False,
                        error="timeout",
                    )
                    raise RuntimeError(
                        f"Custom tool '{tool_record.name}' timed out"
                    )
                except Exception as error:
                    tool_record.increment_usage(
                        success=False,
                        error=str(error),
                    )
                    raise

        _copy_tool_metadata(tracked_tool, original_func)
        return tracked_tool


def _copy_tool_metadata(target: Callable, source: Callable) -> None:
    """Copy name, description, and return_direct metadata."""
    target.name = source.name
    target.description = source.description
    target.__name__ = getattr(source, "__name__", target.name)
    target.return_direct = getattr(source, "return_direct", False)
