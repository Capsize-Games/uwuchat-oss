"""Service-owned LangChain tool manager."""

import inspect
import logging
from collections.abc import Callable
from inspect import Signature
from typing import Any

from airunner_services.llm.core.tool_registry import ToolCategory
from airunner_services.llm.tool_manager_custom import ToolManagerCustomMixin
from airunner_services.llm.tool_manager_selection import (
    ToolManagerSelectionMixin,
)
from airunner_services.llm_workflow_events import (
    build_llm_tool_action_handler,
)
from airunner_services.tools.base_tool import BaseTool

_logger = logging.getLogger(__name__)


def _restore_value(value: Any, vault: Any) -> Any:
    """Restore a single string value through the vault, if it is a string."""
    if not isinstance(value, str):
        return value
    from airunner_services.llm.pii.restorer import restore_text
    return restore_text(value, vault)


def _re_mask_value(value: Any, vault: Any) -> Any:
    """Re-mask a string value: run Presidio detection on fresh PII AND
    re-collapse previously vaulted originals to their placeholders.

    Uses ``mask_text`` which both detects brand-new PII entities (via
    Presidio) and reuses existing placeholders for already-seen values
    (since ``vault.placeholder_for`` returns the same placeholder for
    the same original).
    """
    if not isinstance(value, str) or not value.strip():
        return value
    from airunner_services.llm.pii.masker import mask_text
    return mask_text(value, vault)


class ToolManager(
    BaseTool,
    ToolManagerCustomMixin,
    ToolManagerSelectionMixin,
):
    """Manage LangChain tools for the AIRunner agent."""

    def __init__(
        self,
        rag_manager: Any | None = None,
        tool_action_handler: Any | None = None,
    ):
        self.rag_manager = rag_manager
        self._service_tool_api: Any | None = None
        self._request_tool_defaults: dict[str, Any] = {}
        self._agent: Any = None
        self._pii_vault: Any = None
        self._tool_action_handler = build_llm_tool_action_handler(
            action_handler=tool_action_handler,
            signal_emitter=rag_manager,
        )
        super().__init__(tool_action_handler=self._tool_action_handler)

    def _resolve_tool_api(self, tool_info) -> Any | None:
        """Return the api object injected into a requires_api tool."""
        if tool_info.category == ToolCategory.RAG and self.rag_manager:
            return self.rag_manager
        rag_api = (
            getattr(self.rag_manager, "api", None)
            if self.rag_manager
            else None
        )
        if rag_api is not None:
            return rag_api
        if self._service_tool_api is None:
            try:
                from airunner_services.llm.tools.tool_service_api import (
                    ToolServiceAPI,
                )

                self._service_tool_api = ToolServiceAPI()
            except Exception:
                self.logger.exception(
                    "Failed to build the server tool service api"
                )
                return None
        return self._service_tool_api

    def set_agent(self, agent: Any) -> None:
        """Store the agent object for tools that need user/chatbot context."""
        self._agent = agent

    def _resolve_tool_agent(self, tool_info: Any) -> Any:
        """Return the agent object for tools declaring requires_agent."""
        del tool_info
        return self._agent

    def set_request_tool_defaults(self, defaults: dict[str, Any]) -> None:
        """Set request-scoped default kwargs for tool calls."""
        self._request_tool_defaults = dict(defaults or {})

    def clear_request_tool_defaults(self) -> None:
        """Clear request-scoped tool default kwargs."""
        self._request_tool_defaults = {}

    def set_active_vault(self, vault: Any) -> None:
        """Store the per-request PII vault for de-mask / re-mask."""
        self._pii_vault = vault

    def clear_active_vault(self) -> None:
        """Clear the per-request PII vault."""
        self._pii_vault = None

    def _wrap_tool_with_dependencies(self, tool_info):
        """Wrap one tool function with dependency injection for LangChain."""
        from functools import wraps

        sig, accepted_kwargs, accepts_var_kwargs, visible_params = (
            self._inspect_tool_signature(tool_info)
        )

        @wraps(tool_info.func)
        def wrapped(*args, **kwargs):
            return self._execute_tool(
                tool_info,
                args,
                kwargs,
                accepted_kwargs,
                accepts_var_kwargs,
                sig,
            )

        if sig is not None:
            wrapped.__signature__ = Signature(  # type: ignore[attr-defined]
                parameters=visible_params,
                return_annotation=sig.return_annotation,
            )
        return wrapped

    def _execute_tool(
        self,
        tool_info,
        args,
        kwargs,
        accepted_kwargs,
        accepts_var_kwargs,
        sig,
    ):
        """Execute a tool with dependency injection and error handling."""
        self.logger.debug(
            "Invoking tool: %s args=%s kwargs_keys=%s",
            tool_info.name,
            args,
            list(kwargs.keys()),
        )
        if tool_info.requires_api and (
            accepts_var_kwargs or "api" in accepted_kwargs
        ):
            kwargs.pop("api", None)
            api = self._resolve_tool_api(tool_info)
            if api is None:
                return f"Error: API not available for tool {tool_info.name}"
            kwargs["api"] = api
        if tool_info.requires_agent and (
            accepts_var_kwargs or "agent" in accepted_kwargs
        ):
            kwargs.pop("agent", None)
            agent = self._resolve_tool_agent(tool_info)
            if agent is None:
                return (
                    f"Error: Agent context not available for "
                    f"tool {tool_info.name}"
                )
            kwargs["agent"] = agent
        self._inject_request_defaults(
            kwargs,
            accepted_kwargs,
            accepts_var_kwargs,
            sig,
        )
        self._inject_project_default(
            kwargs, accepted_kwargs, accepts_var_kwargs, sig,
        )

        # ---- PII masking: de-mask args before tool execution ----
        vault = self._pii_vault
        if vault is not None:
            args = tuple(_restore_value(v, vault) for v in args)
            kwargs = {k: _restore_value(v, vault) for k, v in kwargs.items()}

        try:
            result = tool_info.func(*args, **kwargs)
            self.logger.debug(
                "Tool %s returned: %s",
                tool_info.name,
                repr(result)[:200],
            )
            # ---- PII masking: re-mask string return value ----
            if vault is not None and isinstance(result, str):
                result = _re_mask_value(result, vault)
            return result
        except Exception as error:
            import traceback

            error_msg = (
                f"Error executing {tool_info.name}: {error!s}\n"
                f"{traceback.format_exc()}"
            )
            self.logger.error(error_msg)
            return f"Error: {error!s}"

    @staticmethod
    def _inspect_tool_signature(tool_info):
        """Inspect a tool function signature for dependency injection."""
        sig = None
        accepted_kwargs: set[str] = set()
        accepts_var_kwargs = False
        visible_parameters: list = []
        try:
            sig = inspect.signature(tool_info.func)
            for param in sig.parameters.values():
                if param.kind == inspect.Parameter.VAR_KEYWORD:
                    accepts_var_kwargs = True
                elif param.kind in (
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    inspect.Parameter.KEYWORD_ONLY,
                ):
                    accepted_kwargs.add(param.name)
                    if param.name != "api":
                        visible_parameters.append(param)
        except Exception:
            sig = None
        return sig, accepted_kwargs, accepts_var_kwargs, visible_parameters

    def _inject_request_defaults(
        self,
        kwargs,
        accepted_kwargs,
        accepts_var_kwargs,
        sig,
    ) -> None:
        """Inject request-scoped defaults into kwargs when accepted."""
        if not self._request_tool_defaults:
            return
        for key, value in self._request_tool_defaults.items():
            if value is None or key in kwargs:
                continue
            if accepts_var_kwargs or (sig and key in accepted_kwargs):
                kwargs[key] = value

    def _inject_project_default(
        self,
        kwargs,
        accepted_kwargs,
        accepts_var_kwargs,
        sig,
    ) -> None:
        """Inject the single registered project when a code tool omits it.

        The local Qwen code-mode model frequently calls the code proxy
        tools (execute_command, read_file, ...) without ``project_name``
        — the required first parameter — which the ToolManager rejects
        with a generic "Error invoking tool".  When the caller's user
        has exactly ONE registered project, inject its name so the call
        succeeds instead of burning a cycle on a rejection.  A pure
        no-op for non-UwUchat deployments (guarded import).
        """
        if "project_name" in kwargs:
            return
        if not (
            accepts_var_kwargs
            or (sig and "project_name" in accepted_kwargs)
        ):
            return
        import os

        try:
            if os.environ.get("AIRUNNER_PROJECT", "") != "uwuchat":
                return
            from projects.uwuchat.server.models.headlesscode_project import (
                HeadlesscodeProject,
            )

            user_id = getattr(getattr(self._agent, "user", None), "id", None)
            if not user_id:
                return
            projects = HeadlesscodeProject.objects.filter_by(
                user_id=user_id,
            )
            if len(projects) == 1:
                kwargs["project_name"] = projects[0].name
        except Exception:
            return

    def get_all_tools(self, include_deferred: bool = True) -> list[Callable]:
        """Return all available tools for the current request."""
        from airunner_services.llm.core.tool_registry import ToolRegistry

        registry_tools = (
            ToolRegistry.all()
            if include_deferred
            else ToolRegistry.get_immediate_tools()
        )
        tools_by_name: dict[str, Callable] = {}
        for tool_info in registry_tools.values():
            wrapped_func = self._wrap_tool_with_dependencies(tool_info)
            wrapped_func.name = tool_info.name
            wrapped_func.description = tool_info.description
            wrapped_func.return_direct = tool_info.return_direct
            wrapped_func.category = getattr(tool_info, "category", None)
            if tool_info.name in tools_by_name:
                self.logger.warning(
                    "Duplicate tool name in registry: %s — keeping first",
                    tool_info.name,
                )
            tools_by_name[tool_info.name] = wrapped_func
        for custom_tool in self._load_custom_tools():
            name = getattr(custom_tool, "name", None)
            if name and name in tools_by_name:
                self.logger.warning(
                    "Custom tool name conflicts with built-in: %s — custom "
                    "wins",
                    name,
                )
            if name:
                tools_by_name[name] = custom_tool
        return list(tools_by_name.values())

    def get_immediate_tools(self) -> list[Callable]:
        """Return only immediate tools with deferred ones excluded."""
        return self.get_all_tools(include_deferred=False)

    def _get_tool_by_name(self, name: str) -> Callable | None:
        """Return one tool function by name from the registry or mixins."""
        from airunner_services.llm.core.tool_registry import ToolRegistry

        tool_info = ToolRegistry.get(name)
        if not tool_info:
            for registry_tool in ToolRegistry.all().values():
                tool_name = (registry_tool.name or "").lower()
                if tool_name == name.lower() or name.lower() in tool_name:
                    tool_info = registry_tool
                    break
        if tool_info:
            wrapped_func = self._wrap_tool_with_dependencies(tool_info)
            wrapped_func.name = tool_info.name
            wrapped_func.description = tool_info.description
            wrapped_func.return_direct = tool_info.return_direct
            wrapped_func.category = getattr(tool_info, "category", None)
            return wrapped_func
        self.logger.warning("Tool not found in registry: %s", name)
        return None


__all__ = ["ToolManager"]
