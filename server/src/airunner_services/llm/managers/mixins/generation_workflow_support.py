"""Workflow setup helpers for generation."""

from __future__ import annotations

from typing import Any, Dict, Optional

from airunner_services.contract_enums import LLMActionType
from airunner_services.llm.managers.prompt_builder.context import (
    get_prompt_mode,
)
from airunner_services.llm.managers.request_preparation import (
    WorkflowRequestSetup,
    build_workflow_request_setup,
)


def sync_request_scope_to_workflow_manager(owner) -> None:
    """Propagate request-scoped state to the workflow manager.

    Includes request_id, llm_request, and call_chain_id so
    downstream recording paths (_record_stream_usage,
    _record_iteration_usage) can resolve the call chain directly
    from the workflow manager without depending on the ContextVar
    surviving thread / task boundaries inside LangGraph.
    """
    if not owner._workflow_manager:
        return
    request_id = getattr(owner, "_current_request_id", None)
    setattr(
        owner._workflow_manager,
        "llm_request",
        getattr(owner, "llm_request", None),
    )
    # Propagate call_chain_id so per-iteration usage recording inside
    # the DIALOGUE node (which sees the WorkflowManager as its owner)
    # resolves a non-null value via getattr(self._owner, "_call_chain_id").
    call_chain_id = getattr(owner, "_call_chain_id", None)
    if call_chain_id is not None:
        setattr(owner._workflow_manager, "_call_chain_id", call_chain_id)
    if hasattr(owner._workflow_manager, "set_request_id"):
        owner._workflow_manager.set_request_id(request_id)
        return
    setattr(owner._workflow_manager, "_current_request_id", request_id)


def clamp_generation_tokens(owner, generation_kwargs: Dict[str, Any]) -> None:
    """Clamp max_new_tokens to the loaded model context length."""
    target_ctx = getattr(owner, "_target_context_length", None)
    requested = generation_kwargs.get("max_new_tokens")
    if not target_ctx or requested is None:
        return
    if requested > target_ctx:
        owner.logger.info(
            "Clamping max_new_tokens from %s to target context %s",
            requested,
            target_ctx,
        )
        generation_kwargs["max_new_tokens"] = target_ctx


async def setup_generation_workflow(
    owner,
    action: LLMActionType,
    system_prompt: Optional[str],
    skip_tool_setup: bool = False,
    llm_request: Optional[Any] = None,
) -> str:
    """Configure workflow prompts and tools for one generation request."""
    request_setup = build_workflow_request_setup(llm_request)
    if system_prompt:
        action_system_prompt = owner._augment_custom_system_prompt(
            base_prompt=system_prompt,
            action=action,
            include_mood=request_setup.include_mood,
            include_datetime=request_setup.include_datetime,
            include_style=request_setup.include_style,
            include_memory=request_setup.include_memory,
            include_ui_context=request_setup.include_ui_context,
        )
    else:
        action_system_prompt = owner.get_system_prompt_with_context(
            action,
            request_setup.tool_categories,
            request_setup.force_tool,
        )
    apply_workflow_request_setup(
        owner,
        action,
        action_system_prompt,
        skip_tool_setup,
        request_setup,
        system_prompt=system_prompt,
    )
    await _store_per_turn_context(owner, action)
    return action_system_prompt


async def _store_per_turn_context(owner, action: LLMActionType) -> None:
    """Collect dynamic per-request context and store on the workflow manager.

    The system prompt is now stable across requests.  Dynamic content
    (datetime, mood, preflight, rag context, cheap-stage hints) is stored
    here so the prompt assembly layer can inject it into the human turn
    instead.
    """
    wm = getattr(owner, "_workflow_manager", None)
    if wm is None:
        return
    from airunner_services.llm.managers.prompt_builder.per_turn_context import (
        collect_per_turn_context,
    )

    per_turn = await collect_per_turn_context(owner, action)
    rag_ctx = getattr(owner, "_active_rag_context", None) or ""
    if rag_ctx:
        per_turn = f"{per_turn}\n\n{rag_ctx}" if per_turn else rag_ctx
    cheap_hint = getattr(owner, "_cheap_stage_hint", None)
    if cheap_hint:
        per_turn = (
            f"{per_turn}\n\n{cheap_hint}" if per_turn else cheap_hint
        )
        owner._cheap_stage_hint = None
    wm._per_turn_context = per_turn


def apply_workflow_request_setup(
    owner,
    action: LLMActionType,
    action_system_prompt: str,
    skip_tool_setup: bool,
    request_setup: WorkflowRequestSetup,
    system_prompt: Optional[str] = None,
) -> None:
    """Apply one request's workflow settings to the active manager.

    Also computes and stores PromptSegments for Claude models using
    the same real *action* that produced *action_system_prompt*.
    Custom prompts (system_prompt is not None) skip segmentation.
    """
    if not owner._workflow_manager:
        return
    owner._workflow_manager.update_system_prompt(action_system_prompt)

    # Store segmented prompt for Claude multi-breakpoint caching.
    # Only segment when the prompt content matches what
    # build_base_prompt_segments produces — i.e. the plain
    # conversational default branch of get_system_prompt_with_context
    # with no force_tool, no math/precision mode.  For every other
    # branch, explicitly clear segments so a previous turn's stale
    # segments are never reused.
    if system_prompt is None:
        mode = get_prompt_mode(
            getattr(request_setup, "tool_categories", None)
        )
        force_tool = getattr(request_setup, "force_tool", None)
        if mode == "conversational" and not force_tool:
            try:
                segments = owner._build_base_prompt_segments(action)
                # Mirror get_system_prompt_for_action's non-force_tool
                # return: append ACTION_MODE_PROMPTS to the suffix
                # segment so the Claude segmented path produces the
                # same content as the flat path.  (actions.py handles
                # this for the flat string; we do it here for segments.)
                from airunner_services.llm.managers.mixins.system_prompt_action_text import (
                    ACTION_MODE_PROMPTS,
                )
                mode_text = ACTION_MODE_PROMPTS.get(action, "")
                if mode_text:
                    segments.segment_c.append(mode_text.lstrip("\n"))
                owner._workflow_manager.update_prompt_segments(
                    segments
                )
            except Exception:
                owner._workflow_manager.update_prompt_segments(None)
        else:
            owner._workflow_manager.update_prompt_segments(None)
    else:
        owner._workflow_manager.update_prompt_segments(None)

    set_workflow_force_tool(owner, request_setup.force_tool)
    set_workflow_response_format(owner, request_setup.response_format)
    update_workflow_tools_for_action(owner, action, skip_tool_setup)


def set_workflow_force_tool(owner, force_tool: Optional[str]) -> None:
    """Synchronize the request force-tool state into the workflow."""
    if not hasattr(owner._workflow_manager, "set_force_tool"):
        return
    owner._workflow_manager.set_force_tool(force_tool)
    owner.logger.info("Set workflow force_tool to: %s", force_tool)


def set_workflow_response_format(
    owner,
    response_format: Optional[str],
) -> None:
    """Apply one request response-format override when present."""
    if not response_format:
        return
    if not hasattr(owner._workflow_manager, "set_response_format"):
        return
    owner._workflow_manager.set_response_format(response_format)
    owner.logger.info("Set workflow response format to: %s", response_format)


def update_workflow_tools_for_action(
    owner,
    action: LLMActionType,
    skip_tool_setup: bool,
) -> None:
    """Refresh action tools unless request-time filtering already ran."""
    if skip_tool_setup:
        owner.logger.info(
            "Skipping tool setup - tools already filtered by tool_categories"
        )
        return
    if not owner._tool_manager:
        return
    action_tools = owner._tool_manager.get_tools_for_action(action)
    owner._workflow_manager.update_tools(action_tools)
