"""Generation entry point and model-usage event emission.

Extracted from ``generation_execution_support``.  ``do_generate`` is
the main entry point that orchestrates scoring, tier swapping, mood,
workflow setup, streaming, finalization, and summarization.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from airunner_services.contract_enums import LLMActionType
from airunner_services.llm.llm_request import LLMRequest
from airunner_services.llm.pipeline_loader import pipeline_config
from airunner_services.llm.managers.mixins.conversation_summarization import (
    maybe_summarize_checkpoint,
)
from airunner_services.llm.session_manager import touch_session_last_message_at
from airunner_services.llm.managers.mixins.generation_execution_finalize import (
    finalize_generation,
)
from airunner_services.llm.managers.mixins.generation_model_support import (
    ensure_workflow_manager_ready,
    invalid_model_path_response,
)
from airunner_services.llm.managers.mixins.generation_stream_support import (
    executed_tools_from_workflow,
)
from airunner_services.llm.managers.mixins.generation_workflow_support import (
    setup_generation_workflow,
)
from airunner_services.llm.managers.mixins.generation_execution_support._mood import (
    _emit_mood_to_client,
    _persist_auto_mood,
    _update_and_emit_mood,
)
from airunner_services.llm.managers.mixins.generation_execution_support._scheduling import (
    _log_deep_research_action,
    _maybe_schedule_curiosity,
    _maybe_schedule_extraction,
    _schedule_mid_session_tasks,
)
from airunner_services.llm.managers.mixins.generation_execution_support._scoring import (
    _compute_turn_scores,
)
from airunner_services.llm.managers.mixins.generation_execution_support._streaming import (
    run_generation_stream,
)
from airunner_services.llm.managers.mixins.generation_execution_support._tier import (
    _apply_dialogue_tier_model,
    _restore_dialogue_model,
)


async def do_generate(
    owner,
    prompt: str,
    action: LLMActionType,
    system_prompt: Optional[str] = None,
    llm_request: Optional[Any] = None,
    do_tts_reply: bool = True,
    extra_context: Optional[Dict[str, Dict[str, Any]]] = None,
    skip_tool_setup: bool = False,
) -> Dict[str, Any]:
    """Generate a response using the loaded LLM."""
    del do_tts_reply, extra_context
    try:
        from airunner_services.llm.tools.knowledge_tools.record import (
            clear_turn_cache,
        )
        clear_turn_cache()
    except Exception:
        pass
    invalid_path = invalid_model_path_response(owner)
    if invalid_path:
        return invalid_path
    _compute_turn_scores(owner, prompt)
    _apply_dialogue_tier_model(owner)
    _log_deep_research_action(owner, action)
    # Compute fresh mood BEFORE building the prompt so the LLM receives
    # an up-to-date emotional state in its per-turn context.
    mood_payload = _update_and_emit_mood(
        owner, getattr(owner, "_call_chain_id", None)
    )
    if mood_payload:
        owner._current_mood = mood_payload.get("mood", "neutral")
        owner._current_emoji = mood_payload.get("emoji", "😐")
        owner._current_kaomoji = mood_payload.get(
            "kaomoji", "(｡◕ᴗ◕｡)"
        )
        _emit_mood_to_client(owner, mood_payload)
        # Persist auto-mood to conv.user_data so the kaomoji survives
        # browser reload.  The _attach_mood path only fires when
        # update_mood runs as a tool; the auto-mood computed here
        # by intra-session logic must be persisted independently.
        _persist_auto_mood(owner, mood_payload)
        # Stash mood for add_message() to attach directly to this turn's
        # assistant message (set here, before run_generation_stream()
        # triggers the checkpoint write that persists it) — same pattern
        # as _pending_call_chain_id above. update_mood may override this
        # with a more specific self-report later in the same turn via
        # _maybe_restore_mood_state().
        _memory = getattr(owner, "_memory", None)
        if _memory:
            msg_hist = getattr(_memory, "message_history", None)
            if msg_hist is not None:
                msg_hist._pending_bot_mood = mood_payload
    llm_request = llm_request or LLMRequest()
    owner._current_prompt = prompt
    await setup_generation_workflow(
        owner, action, system_prompt, skip_tool_setup, llm_request
    )
    complete_response = [""]
    sequence_counter = [0]
    owner._interrupted = False
    owner._turn_failed = False
    workflow_error = ensure_workflow_manager_ready(owner)
    if workflow_error:
        return workflow_error
    result = run_generation_stream(
        owner, prompt, llm_request, complete_response, sequence_counter
    )
    _record_model_used_event(owner)
    _maybe_schedule_extraction(owner, prompt, complete_response[0])
    _maybe_schedule_curiosity(owner, prompt, complete_response[0], action)
    _schedule_mid_session_tasks(owner)
    wm = getattr(owner, "_workflow_manager", None)
    touch_session_last_message_at(
        getattr(wm, "_conversation_id", None) if wm else None
    )
    # Finalize the visible response BEFORE summarization so the user's
    # reply is safely extracted from the materialized result dict
    # before checkpoint rewriting could affect it.  Summarization
    # rewrites the LangGraph checkpoint state (reassigns
    # state["messages"]), and while result["messages"] is a captured
    # Python list, defensive ordering avoids any subtle interaction
    # between summarization and response finalization.
    if not getattr(owner, "_turn_failed", False):
        executed_tools = executed_tools_from_workflow(
            owner._workflow_manager
        )
        final = finalize_generation(
            owner,
            llm_request,
            result,
            complete_response,
            sequence_counter,
            executed_tools,
            prompt,
        )
        # Push the fresh mood to the client so the kaomoji display updates.
        _emit_mood_to_client(owner, mood_payload)
        from airunner_services.llm.interjection_engine import (
            maybe_schedule_interjection,
        )
        maybe_schedule_interjection(
            owner, prompt, complete_response[0], action
        )
    else:
        final = {"response": complete_response[0], "tools": []}
    # Run summarization AFTER the turn's response has been finalized
    # so it cannot affect what the user sees.  Summarization is a
    # background maintenance task and should never race with the
    # extraction of this turn's reply from the checkpoint.
    maybe_summarize_checkpoint(owner)
    _restore_dialogue_model(owner)
    return final


def _record_model_used_event(owner) -> None:
    """Emit a model_used ConversationEvent for the final response model."""
    try:
        wm = getattr(owner, "_workflow_manager", None)
        if wm is None:
            return
        model_info = getattr(wm, "_current_model_info", None)
        if not model_info:
            return
        chatbot = getattr(wm, "chatbot", None)
        chatbot_id = getattr(chatbot, "id", None) if chatbot else None
        if not chatbot_id:
            return
        from airunner_services.events.recorder import record

        memory = getattr(owner, "_memory", None)
        msg_hist = getattr(memory, "message_history", None) if memory else None
        conversation_id = None
        session_id = None
        if msg_hist is not None:
            conv = getattr(msg_hist, "_conversation", None)
            if conv is not None:
                conversation_id = getattr(conv, "id", None)
                session_id = getattr(conv, "session_id", None)
        record(
            "model_used",
            chatbot_id=chatbot_id,
            actor="assistant",
            payload={
                "pipeline_key": model_info.get("pipeline_key", ""),
                "model_id": model_info.get("model_id", ""),
                "provider": model_info.get("provider", ""),
            },
            conversation_id=conversation_id,
            session_id=session_id,
        )
    except Exception:
        pass
