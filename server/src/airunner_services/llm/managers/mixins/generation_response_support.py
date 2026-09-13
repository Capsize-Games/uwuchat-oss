"""Response extraction and fallback helpers for generation."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage
from langgraph.errors import GraphRecursionError

from airunner_services.llm.gpt_oss_parser import (
    has_gpt_oss_markup,
    looks_like_tool_argument_payload,
    parse_gpt_oss_response,
)
from airunner_services.llm.managers.mixins.generation_signal_support import (
    _send_signal,
)

_logger = logging.getLogger(__name__)

READ_ONLY_TASK_TOOLS = {
    "list_workspace_files",
    "read_code_file",
    "read_file",
    "search_files",
    "grep_search",
    "semantic_search",
    "get_document_content",
    "get_document_info",
    "search_document",
    "goto_document_line",
    "validate_code",
    "run_tests",
    "lint_code",
    "analyze_code_complexity",
    "execute_python",
    # UwUChat code-mode proxy tools (see projects/uwuchat/server/tools/
    # code_tools/) — read-only names so the project override is reached
    # instead of the raw framework diagnostic.
    "list_files",
    "codebase_search",
    "list_registered_projects",
}

STATUS_ONLY_TOOLS = {
    "update_mood",
    "block_user",
    "record_knowledge",
    "record_character_fact",
    "recall_character_facts",
    "recall_knowledge",
    "toggle_tts",
    "clear_conversation",
}

MUTATING_TASK_TOOLS = {
    "create_code_file",
    "edit_code_file",
    "delete_code_file",
    "format_code_file",
    "format_code",
    "write_file",
    "edit_file",
    "delete_file",
    "edit_document_lines",
    "insert_document_lines",
    "delete_document_lines",
    "replace_in_document",
    "save_document",
    # UwUChat code-mode proxy file tools (see projects/uwuchat/server/
    # tools/code_tools/proxy_file_tools.py) — mutating names so the
    # project override is reached instead of the raw framework text.
    "write_to_file",
    "apply_diff",
    "search_replace",
}

# Code-mode proxy command tools that are neither purely read-only nor
# file-mutating (see projects/uwuchat/server/tools/code_tools/).  They
# must always route to the project override — never the raw generic
# diagnostic — so they are checked explicitly in ``_tool_only_fallback``.
_COMMAND_TOOLS = ("execute_command",)


def fallback_response_for_empty_result(
    result: Dict[str, Any],
    executed_tools: List[str],
) -> str:
    """Return a visible fallback when the model produced no final text."""
    messages = _result_messages(result)
    ai_messages = [
        message for message in messages or [] if isinstance(message, AIMessage)
    ]
    effective_tools = list(executed_tools)
    if not effective_tools:
        _extend_tools_from_messages(effective_tools, ai_messages)
    if effective_tools:
        return _tool_only_fallback(effective_tools)
    if any(getattr(message, "tool_calls", None) for message in ai_messages):
        project_msg = _try_project_fallback([])
        if project_msg:
            return project_msg
        return (
            "The model attempted a tool-based response but did not produce "
            "a final reply. No changes were applied."
        )
    if ai_messages:
        project_msg = _try_project_fallback([])
        if project_msg:
            return project_msg
        return (
            "The model produced an empty reply for this request. No changes "
            "were applied."
        )
    return ""


def _result_messages(result: Dict[str, Any]):
    """Return the raw or final messages from one result."""
    if not isinstance(result, dict):
        return []
    return result.get("raw_messages") or result.get("messages")


def _extend_tools_from_messages(
    effective_tools: list[str], ai_messages
) -> None:
    """Extend the executed tool list from AI message metadata."""
    for message in ai_messages:
        extra_tools = (message.additional_kwargs or {}).get("executed_tools")
        if isinstance(extra_tools, (list, tuple, set)):
            effective_tools.extend(
                str(tool_name) for tool_name in extra_tools if tool_name
            )


def _tool_only_fallback(effective_tools: list[str]) -> str:
    """Return the fallback message for tool-only completions."""
    normalized_tools = set(effective_tools)
    if normalized_tools <= STATUS_ONLY_TOOLS:
        return ""
    if normalized_tools & set(_COMMAND_TOOLS):
        # Command tools (e.g. a shell runner) are neither read-only nor
        # file-mutating — always route them to the project override so
        # the raw framework diagnostic never leaks for them.
        message = _try_project_fallback(effective_tools)
        if message:
            return message
        return _framework_tool_fallback(effective_tools)
    message = _try_project_fallback(effective_tools)
    if message:
        return message
    return _framework_tool_fallback(effective_tools)


def _try_project_fallback(effective_tools: list[str]) -> str:
    """Delegate to a project-specific fallback when one is importable.

    Follows the same guarded-import pattern established in
    ``request_handling_mixin._maybe_run_tool_execution_stage``: the
    framework attempts an import from the project package and falls
    back to default behavior when the project module is absent.
    """
    try:
        import importlib
        import os

        project = os.environ.get("AIRUNNER_PROJECT", "")
        if not project:
            from airunner_services.conf import settings

            project = getattr(settings, "AIRUNNER_PROJECT", "") or ""
        if not project:
            return ""
        mod = importlib.import_module(
            f"projects.{project}.server.fallback_response"
        )
        func = getattr(mod, "uwuchat_fallback_response", None)
        if func is None:
            func = getattr(mod, "headlesscode_fallback_response", None)
        if func is None:
            return ""
        return func(effective_tools)
    except ImportError:
        return ""
    except Exception:
        _logger.warning(
            "Project fallback response raised an exception",
            exc_info=True,
        )
        return ""


def _framework_tool_fallback(effective_tools: list[str]) -> str:
    """Return the framework-default fallback for tool-only completions."""
    tool_summary = ", ".join(dict.fromkeys(effective_tools))
    normalized_tools = set(effective_tools)
    if (
        not normalized_tools & MUTATING_TASK_TOOLS
        and normalized_tools <= READ_ONLY_TASK_TOOLS
    ):
        return (
            "The model inspected the workspace with read-only tools "
            f"({tool_summary}) but did not provide a final reply."
        )
    if not normalized_tools & MUTATING_TASK_TOOLS:
        return (
            f"The model used non-mutating tools ({tool_summary}) but "
            "did not produce a final reply synthesizing the results."
        )
    return (
        "The request completed tool actions "
        f"({tool_summary}), but the model did not provide a final reply."
    )


def handle_interrupted_generation(
    owner,
    llm_request: Optional[Any],
    sequence_counter: int,
) -> str:
    """Handle interrupted generation and send an empty end marker."""
    owner.logger.info("Generation interrupted by user")
    _send_signal(
        owner,
        llm_request,
        "",
        is_end_of_message=True,
        sequence_number=sequence_counter + 1,
        message_type="assistant",
    )
    return ""


def _debug_print_error(exc: Exception, error_message: str) -> None:
    """Log error diagnostics for debugging."""
    from airunner_services.utils.network_retry import (
        is_transient_network_error,
    )
    if is_transient_network_error(exc):
        _logger.warning(
            "Exception type: %s; message: %s; error_message: %s",
            type(exc).__name__,
            exc,
            error_message,
        )
    else:
        _logger.error(
            "Exception type: %s; message: %s; error_message: %s",
            type(exc).__name__,
            exc,
            error_message,
            exc_info=True,
        )


def handle_generation_error(
    owner, exc: Exception, llm_request: Optional[Any]
) -> str:
    """Handle generation errors and emit the system error chunk."""
    from airunner_services.utils.network_retry import (
        is_permanent_client_error,
        is_transient_network_error,
        log_network_error_diagnostic,
        mark_api_exhausted,
    )
    if is_permanent_client_error(exc):
        mark_api_exhausted(exc)
    if is_transient_network_error(exc):
        log_network_error_diagnostic(
            owner.logger, "Error during generation", exc
        )
    else:
        owner.logger.error(
            "Error during generation: %s", exc, exc_info=True
        )
    error_message = _generation_error_message(owner, exc)
    _debug_print_error(exc, error_message)
    _send_signal(
        owner,
        llm_request,
        error_message,
        is_end_of_message=False,
        message_type="system",
        is_system_message=True,
    )
    _rollback_stranded_user_turn(owner)
    return error_message


def _rollback_stranded_user_turn(owner) -> None:
    """Remove the user message that was persisted before the reply failed.

    When a turn's reply fails, the user's HumanMessage was already
    checkpointed (persisted to Conversation.value) before the model
    node ran.  This removes that orphaned message and clears the
    in-memory checkpoint state cache so the next get_tuple() rebuilds
    from the (now-correct) database state rather than re-persisting
    the deleted message.
    """
    try:
        wm = getattr(owner, "_workflow_manager", None)
        if wm is None:
            return
        memory = getattr(wm, "_memory", None)
        if memory is None:
            return
        msg_history = getattr(memory, "message_history", None)
        if msg_history is None:
            return
        msg_history.trim_orphaned_user_message()
        # Clear the in-memory checkpoint state for this thread so
        # the next get_tuple() falls through to a fresh DB load.
        thread_id = str(msg_history.conversation_id)
        checkpoint_state = getattr(memory, "_checkpoint_state", None)
        if checkpoint_state is not None and thread_id in checkpoint_state:
            del checkpoint_state[thread_id]
    except Exception as rollback_exc:
        _logger.warning(
            "Failed to roll back stranded user turn: %s: %s",
            type(rollback_exc).__name__,
            rollback_exc,
        )


def _generation_error_message(owner, exc: Exception) -> str:
    """Return the visible error message for one generation exception."""
    if not isinstance(exc, GraphRecursionError):
        from airunner_services.utils.network_retry import (
            extract_user_error_message,
        )
        user_msg = extract_user_error_message(exc)
        if user_msg:
            return f"Error: {user_msg}"
        return "Error: An error occurred while contacting the model."
    executed_tools_value = getattr(
        owner._workflow_manager, "_executed_tools", []
    )
    executed_tools = []
    if isinstance(executed_tools_value, (list, tuple, set)):
        executed_tools = list(executed_tools_value)
    if any(tool in MUTATING_TASK_TOOLS for tool in executed_tools):
        return (
            "Error: The request hit the workflow recursion limit after "
            "applying some tool actions. Changes may already exist in the "
            "workspace, but the model did not finish verification."
        )
    return (
        "Error: The request got stuck repeating tool calls without making "
        "progress and hit the workflow recursion limit. No changes were "
        "applied."
    )


def _find_first_non_tool_message(
    final_messages: list[AIMessage],
) -> Optional[str]:
    """Return the first assistant message with visible content."""
    for message in reversed(final_messages):
        # A message that carries tool calls is never a final narration —
        # the model speaks AFTER the tool result.  Its content is
        # internal scaffolding (some local daemons fill it with a raw
        # diagnostic); never surface it as the reply.
        if getattr(message, "tool_calls", None):
            continue
        final_content = message.content or ""
        if not final_content or looks_like_tool_argument_payload(
            final_content
        ):
            continue
        if has_gpt_oss_markup(final_content):
            parsed = parse_gpt_oss_response(final_content)
            if parsed.content:
                return _normalize_final_content(parsed.content)
            continue
        if "\nAction:" in final_content:
            response_part = final_content.split("\nAction:")[0].strip()
            if response_part:
                return _normalize_final_content(response_part)
            continue
        return _normalize_final_content(final_content)
    return None


def extract_final_response(owner, result: Dict[str, Any]) -> str:
    """Extract the final visible assistant response from one result."""
    final_messages = _final_ai_messages(result)
    if not final_messages:
        owner.logger.info("No final AIMessage found in generation result")
        return ""
    content = _find_first_non_tool_message(final_messages)
    if content is not None:
        return content
    owner.logger.info("Final AIMessage was empty")
    return ""


def _final_ai_messages(result: Dict[str, Any]) -> list[AIMessage]:
    """Return the final AI messages from one generation result."""
    if not result or "messages" not in result:
        return []
    return [
        message
        for message in result["messages"]
        if isinstance(message, AIMessage)
    ]


def _normalize_final_content(content: str) -> str:
    """Strip one leading assistant label from a final model reply."""
    normalized = (content or "").lstrip()
    lowered = normalized.lower()
    for prefix in ("assistant\n", "assistant:"):
        if lowered.startswith(prefix):
            return normalized[len(prefix) :].lstrip()
    return normalized
