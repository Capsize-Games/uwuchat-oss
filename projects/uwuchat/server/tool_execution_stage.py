"""Cheap-model tool-execution stage for UwUchat.

Runs between TOOL_CLASSIFICATION and DIALOGUE generation: a cheap model
(google/gemini-2.5-flash) attempts to execute tool calls for categories
that don't need in-character voice — system, math, research, search.
Any completed tool calls are persisted to conversation history so the
DIALOGUE model (Haiku) sees them as context when writing the final
in-character reply.  When the cheap model cannot proceed (missing info),
it returns a clarification note for Haiku to narrate.

Architecture (see plans/uwuchat-cheap-tool-execution-stage.md):
    TOOL_CLASSIFICATION → TOOL EXECUTION (this stage) → DIALOGUE

Structural template: knowledge_extractor.py _run_agent_loop().

Agent injection for requires_agent tools is handled by ToolManager —
this stage does NOT duplicate that logic.  The tools returned by
tool_manager.get_tools_by_categories() are already wrapped through
ToolManager._wrap_tool_with_dependencies, which routes through
ToolManager._execute_tool where the requires_agent check lives.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from airunner_services.data.tenant import get_tenant_key
from airunner_services.llm.active_call_chain import (
    get_active_call_chain,
)
from airunner_services.llm.agent_loop_cache import (
    compute_message_char_count,
    inject_agent_loop_cache_breakpoint,
)
from airunner_services.llm.managers.database_chat_message_history import (
    DatabaseChatMessageHistory,
)
from airunner_services.llm.pipeline_loader import pipeline_config
from airunner_services.llm.token_usage import record_background_usage

logger = logging.getLogger(__name__)

# Categories routed through the cheap model instead of DIALOGUE.
# image: already uses return_direct=True (bypasses narration).
# knowledge: already has its own async post-hoc path.
# mood / conversation: ALWAYS_INCLUDE_CATEGORIES — cheap, low-iteration,
#   tightly coupled to in-character behavior; stay on DIALOGUE.
_CHEAP_STAGE_CATEGORIES = frozenset({"system", "math", "research", "search"})

# Maximum tool-loop iterations on the cheap model.
_MAX_ITERATIONS = 6

# Hard ceiling on search/scrape-type queries per turn (search_news,
# search_fastsearch, search_fastsearch_news, scrape_website combined).
# Counts *queries within a call's list*, not calls, so batching many
# queries into one call can't bypass the ceiling.  Grounded in
# pipeline_token_usage call counts: normal turns rarely exceed 2-3
# search calls; hitting the cap means the model is issuing too many
# individual queries rather than narrowing its request.
_MAX_SEARCH_QUERIES = 5

# Hard ceiling on total tool-execution rounds per turn — separate
# from _MAX_ITERATIONS to catch unbatching without blocking
# legitimate multi-tool turns entirely.
_MAX_TOOL_ROUNDS = 4

_SYSTEM_PROMPT = (
    "You are a tool-execution assistant. Your ONLY job is to call tools.\n\n"
    "Rules:\n"
    "1. Read the user's message below and decide which tool(s) to call.\n"
    "2. Call the tool with the correct arguments — do NOT guess or invent.\n"
    "3. If you have enough information, call the tool. Do NOT write a reply.\n"
    "4. If you are MISSING required information (e.g. no date/time for "
    "a calendar event, no search query), produce a SHORT factual note "
    "in this exact format:\n"
    '   NEEDS_CLARIFICATION: <what is missing>\n'
    "5. Do NOT write in character. Do NOT be conversational.\n"
    "6. After all tools have been called and results are in, "
    "output DONE.\n"
    "7. CRITICAL — BATCH: If a tool accepts a LIST parameter "
    "(queries, facts, candidates, claims), put EVERYTHING into ONE "
    "call with the full list. NEVER call the same tool repeatedly "
    "with one item each. ONE call with N items, not N calls.\n\n"
    "Examples:\n"
    '  User: "Remind me about my dentist appointment next Tuesday at 2pm"\n'
    "  → Call add_calendar_event, then output DONE.\n\n"
    '  User: "I have a dentist appointment coming up"\n'
    "  → NEEDS_CLARIFICATION: no date/time given for "
    "calendar event\n\n"
    '  User: "What is 15% of 83.50?"\n'
    "  → Call calculator, then output DONE.\n\n"
    '  User: "Look up the latest on AI and climate policy"\n'
    '  → Call search_fastsearch with queries=["latest AI", '
    '"climate policy"], then output DONE. (BATCHED — not two calls.)\n'
)


def _categories_to_run(
    selected_categories: list[str] | None,
) -> set[str]:
    """Return the subset of categories that the cheap stage handles.

    When either ``search`` or ``research`` is selected, both are
    included so that search_news (SEARCH) and search_fastsearch_news
    (RESEARCH) are always available together — the model should never
    have to guess which tool name is bound in the current category set.
    """
    if not selected_categories:
        return set()
    categories = set(selected_categories) & _CHEAP_STAGE_CATEGORIES
    if "search" in categories or "research" in categories:
        categories.add("search")
        categories.add("research")
    return categories


def _build_tool_map(tools: list) -> dict[str, Any]:
    """Build a name→wrapped-function map from tools returned by ToolManager.

    Each tool is already wrapped through
    ToolManager._wrap_tool_with_dependencies, which routes through
    ToolManager._execute_tool — the single place where requires_api,
    requires_agent, and request-level defaults are injected.
    """
    tool_map: dict[str, Any] = {}
    for tool in tools:
        name = getattr(tool, "name", None)
        if name:
            tool_map[name] = tool
    return tool_map


def _execute_tool_via_manager(
    tc: dict,
    tool_map: dict[str, Any],
) -> str:
    """Dispatch one tool call through ToolManager's wrapped functions.

    Each wrapped function delegates to ToolManager._execute_tool, which
    handles requires_agent, requires_api, and request_defaults centrally.
    """
    name = tc.get("name", "")
    args = dict(tc.get("args", {}) or {})
    tool_func = tool_map.get(name)
    if tool_func is None:
        return f"Unknown tool: {name}"
    try:
        return str(tool_func(**args))
    except Exception as exc:
        logger.debug("Tool %s error: %s", name, exc)
        return f"Tool error: {exc}"


def _tool_execution_label(tool_calls: list) -> str:
    """Pipeline_key label for one TOOL_EXECUTION iteration."""
    return (
        "TOOL_EXECUTION (tool call)" if tool_calls
        else "TOOL_EXECUTION (response)"
    )


def _response_text(response: Any) -> str:
    """Extract response content as a string, or empty string."""
    content = getattr(response, "content", None)
    return str(content) if content else ""


def _record_iteration_usage(
    response: Any,
    tool_calls: list,
    chatbot_id: int,
    messages: list[BaseMessage],
) -> None:
    """Record PipelineTokenUsage for one iteration.  Never raises."""
    try:
        from airunner_services.llm.token_usage import (
            record_pipeline_call_text,
        )

        msg_char_count = compute_message_char_count(messages)
        usage_id = record_background_usage(
            _tool_execution_label(tool_calls),
            pipeline_config("TOOL_EXECUTION"),
            response,
            chatbot_id=chatbot_id,
            tenant_key=get_tenant_key(),
            call_chain_id=get_active_call_chain(),
            prompt_char_count=msg_char_count,
            response_char_count=len(_response_text(response)),
        )
        record_pipeline_call_text(
            usage_id=usage_id,
            tenant_key=get_tenant_key(),
            prompt_text=_SYSTEM_PROMPT,
            response_text=_response_text(response),
        )
    except Exception:
        logger.debug(
            "Tool execution: Failed to record usage",
            exc_info=True,
        )


def _emit_tool_status(
    event_sink: Any,
    *,
    tool_id: str,
    tool_name: str,
    tool_args: dict,
    status: str,
    conversation_id: int,
    request_id: Optional[str],
    details: Optional[str] = None,
) -> None:
    """Emit one tool-status event through *event_sink*, never raising.

    Matches the event shape used by
    :meth:`ToolExecutionMixin._emit_starting_status` and
    :meth:`ToolExecutionMixin._emit_completed_status` so the client
    renders these events identically to DIALOGUE-stage tool status
    updates.
    """
    import datetime as _dt

    try:
        query = (
            tool_args.get("query")
            or tool_args.get("search_query")
            or tool_args.get("prompt")
            or str(tool_args)[:50]
        )
        event_sink.emit_tool_status({
            "tool_id": tool_id,
            "tool_name": tool_name,
            "query": query,
            "status": status,
            "details": details,
            "conversation_id": conversation_id,
            "request_id": request_id,
            "timestamp": str(_dt.datetime.now()),
        })
    except Exception:
        pass


def _emit_thinking_event(
    event_sink: Any,
    *,
    status: str,
    request_id: Optional[str],
) -> None:
    """Emit one thinking-status event through *event_sink*, never raising.

    Uses the same event shape as
    :meth:`ToolClassificationMixin._emit_classification_thinking_event`
    so the client renders these identically to the existing
    "Thinking..." status bubble.
    """
    try:
        event_sink.emit_thinking({
            "status": status,
            "content": "",
            "request_id": request_id,
        })
    except Exception:
        pass


def run_tool_execution_stage(
    *,
    chat_model: Any,
    tool_manager: Any,
    prompt: str,
    conversation_id: int,
    selected_categories: list[str] | None,
    chatbot_id: Optional[int] = None,
    event_sink: Optional[Any] = None,
    request_id: Optional[str] = None,
) -> dict:
    """Run the cheap-model tool-execution stage for one user turn.

    Agent context (chatbot + user) must be set on tool_manager via
    tool_manager.set_agent(...) before calling this function.  The
    wrapped tools returned by get_tools_by_categories() route through
    ToolManager._execute_tool, which handles requires_agent injection.

    Args:
        chat_model: The cheap chat model (google/gemini-2.5-flash).
        tool_manager: ToolManager instance with agent already set.
        prompt: The user's message text.
        conversation_id: Conversation ID for persisting tool messages.
        selected_categories: Categories selected by TOOL_CLASSIFICATION.
        event_sink: Optional LLMWorkflowEventSink for emitting
            tool-status events to the client.  When None, status
            events are silently dropped.
        request_id: Optional request ID for event correlation.

    Returns:
        dict with keys:
            tools_executed: bool — True if any tool was called.
            clarification_note: str|None — set when the cheap model needs
                more info from the user; should be narrated by DIALOGUE.
            executed_categories: set[str] — categories whose tools ran.
            tool_results: list[str] — "name: result" strings for each
                tool that executed; surfaced to DIALOGUE as context.
    """
    categories = _categories_to_run(selected_categories)
    if not categories:
        return {
            "tools_executed": False,
            "clarification_note": None,
            "executed_categories": set(),
        }

    from airunner_services.llm.core.tool_registry import ToolCategory

    tool_category_enums = [ToolCategory(c) for c in categories]
    tools = tool_manager.get_tools_by_categories(
        tool_category_enums,
        include_deferred=True,
    )
    if not tools:
        logger.debug(
            "Tool execution stage: no tools for categories %s", categories
        )
        return {
            "tools_executed": False,
            "clarification_note": None,
            "executed_categories": set(),
        }

    tool_map = _build_tool_map(tools)
    available_tool_names = sorted(tool_map.keys())
    bound = chat_model.bind_tools(tools)
    history = DatabaseChatMessageHistory(
        conversation_id,
        call_chain_id=get_active_call_chain(),
    )

    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ]

    tools_executed = False
    clarification_note: Optional[str] = None
    executed_category_set: set[str] = set()
    tool_results: list[str] = []

    # Resolve a concrete event sink, defaulting to a no-op so existing
    # callers (including tests) are unchanged when the parameter is
    # omitted.
    if event_sink is None:
        from airunner_services.llm_workflow_events import (
            NullLLMWorkflowEventSink,
        )
        event_sink = NullLLMWorkflowEventSink()

    # ---- PII masking: vault from ToolManager ----
    vault = getattr(tool_manager, "_pii_vault", None)

    # Store available tool names as a metadata entry in the
    # conversation so the Flow Detail inspector panel can surface
    # which tools were offered to the model for this stage call.
    # The metadata_type tag is recognised by
    # DatabaseChatMessageHistory._is_metadata_entry → filtered from
    # LLM context by the .messages property so it never pollutes
    # the model's conversation view on future turns.
    import datetime as _dt

    now = _dt.datetime.now(_dt.timezone.utc).isoformat()
    available_tools_entry = {
        "role": "system",
        "name": "Available Tools",
        "content": (
            "Available tools: " + ", ".join(available_tool_names)
        ),
        "timestamp": now,
        "metadata_type": "available_tools",
        "available_tools": available_tool_names,
    }
    history.add_metadata_entry(available_tools_entry)

    # Per-turn counters for hard ceilings.
    tool_rounds = 0
    search_queries = 0

    # Emit thinking-started once for the entire cheap-stage loop
    # so the client shows "Thinking..." throughout — not just
    # during individual bound.invoke() calls but also across
    # inter-iteration bookkeeping (PII masking, cache injection,
    # tool execution, DB writes).
    _emit_thinking_event(
        event_sink,
        status="started",
        request_id=request_id,
    )
    _thinking_completed = False

    for iteration in range(_MAX_ITERATIONS):
        # Hard ceilings: stop processing further tool rounds when
        # limits are hit.  Emit a short note so DIALOGUE can narrate
        # that not everything could be checked rather than silently
        # truncating.
        if tool_rounds >= _MAX_TOOL_ROUNDS:
            if not clarification_note:
                clarification_note = (
                    "I found some information but couldn't check "
                    "everything you asked — there were too many "
                    "tools to run."
                )
            _emit_thinking_event(
                event_sink,
                status="completed",
                request_id=request_id,
            )
            _thinking_completed = True
            break

        # Mask messages before each LLM call so the cheap model
        # (TOOL_EXECUTION) never sees raw PII.
        if vault is not None:
            from airunner_services.llm.pii.masker import (
                mask_langchain_messages,
            )
            call_messages = mask_langchain_messages(messages, vault)
        else:
            call_messages = list(messages)

        # After the first iteration, mark the last message from the
        # previous round with cache_control so the provider can serve
        # the unchanged prefix from cache on subsequent calls.
        if iteration > 0:
            call_messages = inject_agent_loop_cache_breakpoint(
                call_messages,
            )

        response = bound.invoke(call_messages)
        messages.append(response)
        tool_calls = getattr(response, "tool_calls", None) or []
        if chatbot_id is not None:
            _record_iteration_usage(
                response, tool_calls, chatbot_id, call_messages,
            )
        if not tool_calls:
            content = getattr(response, "content", "") or ""
            if isinstance(content, str) and content.startswith(
                "NEEDS_CLARIFICATION:"
            ):
                clarification_note = content[
                    len("NEEDS_CLARIFICATION:"):
                ].strip()
                logger.info(
                    "Tool execution: clarification needed — %s",
                    clarification_note,
                )
            _emit_thinking_event(
                event_sink,
                status="completed",
                request_id=request_id,
            )
            _thinking_completed = True
            break

        # Got tool calls — this counts as one round.
        tool_rounds += 1

        if isinstance(response, AIMessage):
            history.add_message(response)

        for tc in tool_calls:
            tc_name = tc.get("name", "")
            tc_args = dict(tc.get("args", {}) or {})
            tc_id = tc.get("id", "")

            # Emit "starting" status before execution.
            _emit_tool_status(
                event_sink,
                tool_id=tc_id,
                tool_name=tc_name,
                tool_args=tc_args,
                status="starting",
                conversation_id=conversation_id,
                request_id=request_id,
            )

            if tc_name in (
                "search_news", "search_fastsearch",
                "search_fastsearch_news", "scrape_website",
            ):
                # Count queries within this call (1 for
                # scrape_website which takes a single URL; N
                # for search tools which take a queries list).
                queries_in_call = len(
                    tc_args.get("queries", [tc_args.get("url", "")])
                )
                if (
                    search_queries + queries_in_call
                    > _MAX_SEARCH_QUERIES
                ):
                    # Ceiling hit — still append a ToolMessage so
                    # every tool_call_id has a response.
                    skip_msg = (
                        "Could not search for everything — "
                        "too many queries in one turn. "
                        "Try asking about fewer things at once."
                    )
                    tool_msg = ToolMessage(
                        content=skip_msg, tool_call_id=tc_id,
                    )
                    messages.append(tool_msg)
                    history.add_message(tool_msg)
                    tool_results.append(
                        f"{tc_name}: {skip_msg}"
                    )
                    _emit_tool_status(
                        event_sink,
                        tool_id=tc_id,
                        tool_name=tc_name,
                        tool_args=tc_args,
                        status="completed",
                        conversation_id=conversation_id,
                        request_id=request_id,
                        details="limit reached",
                    )
                    continue
                search_queries += queries_in_call

            result = _execute_tool_via_manager(tc, tool_map)
            tool_results.append(f"{tc_name}: {result}")
            tool_msg = ToolMessage(content=result, tool_call_id=tc_id)
            messages.append(tool_msg)
            history.add_message(tool_msg)
            tools_executed = True

            # Track which category this tool belongs to.
            from airunner_services.llm.core.tool_registry import ToolRegistry

            tc_info = ToolRegistry.get(tc_name)
            if tc_info:
                executed_category_set.add(tc_info.category.value)

            # Emit "completed" status after execution.
            _emit_tool_status(
                event_sink,
                tool_id=tc_id,
                tool_name=tc_name,
                tool_args=tc_args,
                status="completed",
                conversation_id=conversation_id,
                request_id=request_id,
            )

    if not _thinking_completed:
        _emit_thinking_event(
            event_sink,
            status="completed",
            request_id=request_id,
        )

    if not tools_executed and not clarification_note:
        content = ""
        last_msg = messages[-1] if messages else None
        if last_msg and hasattr(last_msg, "content"):
            content = getattr(last_msg, "content", "") or ""
        if isinstance(content, str) and "DONE" in content.upper():
            logger.debug("Tool execution stage: no tools called (DONE only)")

    return {
        "tools_executed": tools_executed,
        "clarification_note": clarification_note,
        "executed_categories": executed_category_set,
        "attempted_categories": categories,
        "tool_results": tool_results,
    }
