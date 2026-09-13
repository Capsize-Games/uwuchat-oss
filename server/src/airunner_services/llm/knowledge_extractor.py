"""Background knowledge extraction after each LLM response turn.

Flow per completed response:
  1. Daemon thread starts with the last user + assistant messages.
  2. An extractor LLM is given three tools:
       - check_similar_facts(candidate) — TF-IDF search of the KB
       - save_fact(fact, subject) — writes if add_fact() deems it new
       - retract_fact(old_fact_text) — soft-deletes a contradicted fact
  3. Corrections are handled first: if the user corrects the assistant,
     the extractor finds and retracts the old wrong fact then saves the
     correct one.
  4. LLM identifies new candidates, checks each against the KB, and saves
     only what it judges as genuinely new after seeing the search results.

Dedup is two-layered:
  - Primary: LLM sees actual KB matches and decides semantically.
  - Secondary: add_fact() algorithmic duplicate check (text/entity/word
    overlap) runs regardless as a backstop.
"""

from __future__ import annotations

import logging

from airunner_services.utils.network_retry import retry_on_network
from pydantic import BaseModel, Field

from airunner_services.entity_resolver import normalize_entity_type
from airunner_services.llm.knowledge_extractor_prompts import _SYSTEM

logger = logging.getLogger(__name__)


class _FactItem(BaseModel):
    """A single fact to save with its subject, entity, and entity type."""

    fact: str = Field(description="The fact text to save.")
    subject: str = Field(
        default="user",
        description="'user' for facts about the user, 'self' for "
        "facts the character established about themselves, "
        "'world' for facts about a third party, place, thing, "
        "organization, concept, or event.",
    )
    entity_name: str = Field(
        default="",
        description="When this fact is about a specific named "
        "person or entity, provide their name for resolution.",
    )
    entity_type: str = Field(
        default="person",
        description="The type of entity: person, place, thing, "
        "concept, organization, or event.  Only used when "
        "entity_name is also provided.",
    )


def schedule_extraction(
    chatbot_id: int,
    user_text: str,
    assistant_text: str,
    chat_model,
    tenant_key: "str | None" = None,
    conversation_id: "int | None" = None,
    call_chain_id: "str | None" = None,
    account_id: "int | None" = None,
    grounding_sources: str = "",
) -> None:
    """Enqueue a Celery task for background knowledge extraction.

    Replaces the raw ``threading.Thread`` spawn with a Celery task
    on the ``default`` queue.  Tier-2: writes DEK to relay before
    enqueuing so the worker can decrypt ``KnowledgeFact.fact_text``.

    *grounding_sources*: newline-joined search/tool result text from
    the current turn, used by the extractor to evaluate whether a
    ``subject="world"`` fact is grounded in a real tool result.
    """
    from airunner_services.utils.network_retry import is_api_exhausted
    if is_api_exhausted():
        return
    if not user_text or not assistant_text:
        return
    if not tenant_key or not account_id or not conversation_id:
        logger.warning(
            "[EXTRACTOR] Missing tenant_key/account_id/conversation_id — "
            "skipping extraction"
        )
        return

    # Write DEK to relay (Tier 2 hand-off).
    from airunner_services.utils.crypto.dek_cache import get_user_dek
    from airunner_services.tasks.task_helpers import wrap_dek_for_relay
    from airunner_services.tasks.redis_client import dek_relay_store

    user_dek = get_user_dek()
    if user_dek is not None:
        wrapped = wrap_dek_for_relay(user_dek)
        dek_relay_store(account_id, wrapped)

    from airunner_services.tasks.knowledge_tasks import extract_knowledge

    extract_knowledge.apply_async(
        args=[
            tenant_key,
            account_id,
            chatbot_id,
            user_text,
            assistant_text,
            conversation_id,
            call_chain_id or "",
            grounding_sources,
        ],
        queue="default",
    )


def _extract_and_store(
    chatbot_id: int,
    user_text: str,
    assistant_text: str,
    chat_model,
    tenant_key: "str | None" = None,
    conversation_id: "int | None" = None,
    call_chain_id: "str | None" = None,
) -> None:
    """Thread target: run the extractor agent loop."""
    from airunner_services.data.tenant import tenant_scope

    # TEMPORARY: confirm which model the extractor receives (Part 3)
    model_label = getattr(chat_model, "model_name", chat_model)
    logger.info(
        "[EXTRACTOR] model received: %s", model_label,
    )

    try:
        with tenant_scope(tenant_key):
            tools, tools_map = _make_extractor_tools(chatbot_id)
            bound = chat_model.bind_tools(tools)
            _invoke_with_retry(
                chatbot_id, user_text, assistant_text, bound,
                tools_map, conversation_id, call_chain_id,
            )
    except Exception as exc:
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
                logger, "[EXTRACTOR] Network failure", exc,
            )
        else:
            logger.error("[EXTRACTOR] Failed: %s", exc)


@retry_on_network(max_retries=1, backoff=0.5)
def _invoke_with_retry(
    chatbot_id: int,
    user_text: str,
    assistant_text: str,
    bound_model,
    tools_map: dict,
    conversation_id: "int | None" = None,
    call_chain_id: "str | None" = None,
    grounding_sources: str = "",
) -> None:
    """Invoke the extractor agent loop with retry on network errors."""
    _run_agent_loop(
        chatbot_id, user_text, assistant_text, bound_model,
        tools_map, conversation_id, call_chain_id,
        grounding_sources=grounding_sources,
    )


def _check_extractor_truncation(response) -> None:
    """Log when KNOWLEDGE extractor generation was cut off by max_tokens.

    OpenAI-compatible APIs return ``finish_reason: "length"`` when
    generation was truncated.  For the fact extractor this almost
    certainly means a malformed JSON tool call and silently dropped
    facts — log at WARNING.
    """
    metadata = getattr(response, "response_metadata", None) or {}
    finish_reason = metadata.get("finish_reason", "")
    usage = metadata.get("token_usage", {}) or {}
    completion_tokens = usage.get("completion_tokens", 0)
    if finish_reason == "length":
        logger.warning(
            f"[EXTRACTOR TRUNCATION] Generation cut off by max_tokens "
            f"(finish_reason={finish_reason!r}, "
            f"completion_tokens={completion_tokens}) — tool-call "
            f"arguments may be truncated."
        )
    elif finish_reason:
        logger.debug(
            f"[EXTRACTOR] Finished naturally "
            f"(finish_reason={finish_reason!r})"
        )


def _run_agent_loop(
    chatbot_id: int,
    user_text: str,
    assistant_text: str,
    bound_model,
    tools_map: dict,
    conversation_id: "int | None" = None,
    call_chain_id: "str | None" = None,
    grounding_sources: str = "",
) -> None:
    """Drive the check→save tool loop until the model stops calling tools."""
    from langchain_core.messages import (
        AIMessage,
        BaseMessage,
        HumanMessage,
        SystemMessage,
        ToolMessage,
    )
    from airunner_services.knowledge_context import set_knowledge_chatbot_id
    from airunner_services.llm.agent_loop_cache import (
        compute_message_char_count,
        inject_agent_loop_cache_breakpoint,
    )

    set_knowledge_chatbot_id(chatbot_id)
    history = None
    if conversation_id is not None:
        from airunner_services.llm.managers.database_chat_message_history \
            import DatabaseChatMessageHistory
        history = DatabaseChatMessageHistory(
            conversation_id,
            call_chain_id=call_chain_id,
        )

    assistant_block = f"Assistant: {assistant_text}"
    if grounding_sources:
        assistant_block += (
            f"\n\n[Grounding Sources]\n{grounding_sources}"
        )

    messages: list[BaseMessage] = [
        SystemMessage(content=_SYSTEM),
        HumanMessage(
            content=f"User: {user_text}\n{assistant_block}"
        ),
    ]
    for iteration in range(12):
        # After the first iteration, mark the last message from the
        # previous round with cache_control so the provider can serve
        # the unchanged prefix from cache on subsequent calls.
        if iteration > 0:
            call_messages = inject_agent_loop_cache_breakpoint(
                messages,
            )
        else:
            call_messages = list(messages)

        response = bound_model.invoke(call_messages)
        messages.append(response)
        _check_extractor_truncation(response)
        # Record usage so the extractor has a PipelineTokenUsage row
        # that the call-chain API can surface with real cost data.
        if call_chain_id:
            try:
                from airunner_services.llm.pipeline_loader import (
                    pipeline_config,
                )
                from airunner_services.llm.token_usage import (
                    record_background_usage,
                    record_pipeline_call_text,
                )
                from airunner_services.data.tenant import get_tenant_key
                cfg = pipeline_config("KNOWLEDGE")
                # Disambiguate tool-call iterations from the final
                # response iteration, mirroring _iteration_label() in
                # node_streaming_response_helper.py.
                has_tools = bool(
                    getattr(response, "tool_calls", None)
                )
                label = (
                    "KNOWLEDGE (tool call)"
                    if has_tools
                    else "KNOWLEDGE (response)"
                )
                resp_text = getattr(response, "content", None)
                msg_char_count = compute_message_char_count(call_messages)
                usage_id = record_background_usage(
                    label, cfg, response,
                    chatbot_id=chatbot_id,
                    tenant_key=get_tenant_key(),
                    call_chain_id=call_chain_id,
                    prompt_char_count=msg_char_count,
                    response_char_count=len(resp_text) if resp_text else None,
                )
                record_pipeline_call_text(
                    usage_id=usage_id,
                    tenant_key=get_tenant_key(),
                    prompt_text=_SYSTEM,
                    response_text=str(resp_text or ""),
                )
            except Exception:
                logger.debug(
                    "[EXTRACTOR] Failed to record usage", exc_info=True,
                )
        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            break
        if history is not None and isinstance(response, AIMessage):
            history.add_message(response)
        for tc in tool_calls:
            result = _execute_tool(tc, tools_map)
            tool_msg = ToolMessage(
                content=result, tool_call_id=tc["id"]
            )
            messages.append(tool_msg)
            if history is not None:
                history.add_message(tool_msg)


def _make_extractor_tools(chatbot_id: int) -> tuple[list, dict]:
    """Build check and save tools closed over the KB for this chatbot."""
    from langchain_core.tools import StructuredTool
    from airunner_services.knowledge import get_knowledge_base
    from airunner_services.knowledge_context import (
        set_knowledge_chatbot_id,
        set_knowledge_subject,
    )

    kb = get_knowledge_base()

    def _check_many(candidates: list[str]) -> str:
        """Search KB for facts similar to each candidate, in one call."""
        set_knowledge_chatbot_id(chatbot_id)
        results = []
        for candidate in candidates:
            matches = kb.search_facts(candidate, limit=3)
            if not matches:
                results.append(
                    f'"{candidate}": no similar facts found.'
                )
            else:
                lines = "; ".join(m.fact_text for m in matches)
                results.append(f'"{candidate}": {lines}')
        return "\n".join(results)

    def _save_many(facts: list[_FactItem]) -> str:
        """Write one or more facts to the KB in a single call.

        Each element may be a plain dict (raw LLM tool-call args that
        bypass StructuredTool validation — see _execute_tool) or a
        pre-validated _FactItem.  Coerce defensively.
        """
        from airunner_services.entity_resolver import (
            resolve_entity,
        )

        results = []
        for raw in facts:
            item = (
                raw if isinstance(raw, _FactItem)
                else _FactItem(**raw)
            )
            set_knowledge_chatbot_id(chatbot_id)
            set_knowledge_subject(item.subject)

            # Resolve entity if the fact targets a named entity, using
            # the caller-supplied entity_type (default "person").
            entity_id: int | None = None
            if item.entity_name and item.entity_name.strip():
                entity_id = resolve_entity(
                    name=item.entity_name.strip(),
                    chatbot_id=chatbot_id,
                    entity_type=normalize_entity_type(
                        item.entity_type,
                    ),
                    source_type="conversation",
                )

            ok = kb.add_fact(
                item.fact, entity_id=entity_id,
                source_type="inferred",
            )
            verb = "Saved" if ok else "Skipped duplicate"
            results.append(f"{verb}: {item.fact[:80]}")
        return "\n".join(results)

    def _retract(old_fact_text: str) -> str:
        """Remove an incorrect or contradicted fact from the KB."""
        set_knowledge_chatbot_id(chatbot_id)
        ok, count = kb.delete_fact(old_fact_text)
        if ok:
            logger.debug(
                "[EXTRACTOR] Retracted %d fact(s)", count,
            )
            return f"Retracted {count} fact(s): {old_fact_text[:80]}"
        return f"No matching fact found to retract: {old_fact_text[:80]}"

    check_tool = StructuredTool.from_function(
        func=_check_many,
        name="check_similar_facts",
        description=(
            "Search the knowledge base for facts similar to one or more "
            "candidates in a single call.  Pass every candidate fact you "
            "found this turn as one list — do not call this multiple "
            "times in the same turn.  Always call this before save_fact "
            "or retract_fact."
        ),
    )
    save_tool = StructuredTool.from_function(
        func=_save_many,
        name="save_fact",
        description=(
            "Save one or more new facts to the knowledge base in a "
            "single call.  Pass every new fact you found this turn as "
            "one list — do not call this multiple times in the same "
            "turn.  subject='user' for user facts, 'self' for "
            "character facts, 'world' for facts about third parties, "
            "places, things, organizations, concepts, or events."
        ),
    )
    retract_tool = StructuredTool.from_function(
        func=_retract,
        name="retract_fact",
        description=(
            "Delete an incorrect or now-contradicted fact from the knowledge"
            " base. Pass the exact or partial text of the old fact to remove."
            " Use this when the user corrects something the assistant got wrong."
        ),
    )
    tools_map = {
        "check_similar_facts": _check_many,
        "save_fact": _save_many,
        "retract_fact": _retract,
    }
    return [check_tool, save_tool, retract_tool], tools_map


def _execute_tool(tc: dict, tools_map: dict) -> str:
    """Dispatch one tool call and return the result string."""
    name = tc.get("name", "")
    args = tc.get("args", {}) or {}
    fn = tools_map.get(name)
    if fn is None:
        return f"Unknown tool: {name}"
    try:
        return str(fn(**args))
    except Exception as exc:
        logger.debug("[EXTRACTOR] Tool %s error: %s", name, exc)
        return f"Tool error: {exc}"
