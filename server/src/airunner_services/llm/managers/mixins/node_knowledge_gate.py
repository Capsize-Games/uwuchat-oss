"""Knowledge gate — scatter-gather concern dispatch for each turn."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from airunner_services.llm.managers.concerns import (
    ConcernDispatcher,
    RecallConcern,
    SaveConcern,
    SearchConcern,
)

NO_RESULTS_REPLY = (
    "Honestly, I'm not sure about that one — I don't have reliable"
    " information on it. If you can give me more detail or a different"
    " angle, I'll try to help."
)

_SEARCH_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "get_topic_brief",
        "search_news",
        "search_fastsearch",
        "search_fastsearch_news",
    }
)

_EMPTY_MARKERS: tuple[str, ...] = (
    '"results": []',
    "no results",
    "no news results",
    "rate-limited",
    "unavailable",
    "0 results",
    "nothing found",
    "no relevant",
    '"brief": null',
    "no topic brief found",
    "topic brief lookup failed",
)


class NodeKnowledgeGate:
    """Pre-flight node that fans out concern classifiers in parallel."""

    def __init__(self, owner: Any) -> None:
        """Store the owning workflow manager."""
        self._owner = owner

    # ------------------------------------------------------------------
    # Node entry point
    # ------------------------------------------------------------------

    def knowledge_gate(
        self, state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Run all concern classifiers in parallel and inject tool calls."""
        self._reset_turn_caches()
        msgs = state["messages"]
        user_text = self._last_human_text(msgs)
        if not user_text:
            return {}
        context = self._conversation_context(msgs)
        model = self._get_fast_model()
        bound = self._bound_tool_names()

        concerns = self._build_concerns(bound)
        dispatcher = ConcernDispatcher(concerns, model)
        fired = dispatcher.dispatch(user_text, context)

        if not fired:
            self._owner.logger.info("[GATE] No concerns fired")
            return {}

        tool_messages: list[AIMessage] = []
        for tool_name, args in fired:
            resolved_name = args.pop("__tool_name", tool_name)
            self._owner.logger.info(
                "[GATE] %s fired → %s(%r)",
                tool_name,
                resolved_name,
                args,
            )
            tool_messages.append(
                self._make_tool_call_message(
                    resolved_name, args
                )
            )
        return {"messages": tool_messages}

    # ------------------------------------------------------------------
    # Concern factory
    # ------------------------------------------------------------------

    def _build_concerns(
        self, bound: frozenset[str]
    ) -> list:
        """Return all concern classifiers that have tools available."""
        concerns: list = []
        if any(t in bound for t in _SEARCH_TOOL_NAMES):
            concerns.append(SearchConcern(bound))
        if "recall_knowledge" in bound:
            concerns.append(RecallConcern())
        if "save_knowledge" in bound:
            concerns.append(SaveConcern())
        return concerns

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def route_after_gate(self, state: Dict[str, Any]) -> str:
        """Route to tools when any injected message has tool calls."""
        msgs = state.get("messages", [])
        # The gate may inject multiple AIMessage tool-call messages
        # in one turn.  Check the last N messages (one per possible
        # concern) rather than only the final one.
        for msg in reversed(msgs[-3:]):
            if (
                isinstance(msg, AIMessage)
                and getattr(msg, "tool_calls", None)
            ):
                return "tools"
        return "model"

    # ------------------------------------------------------------------
    # Shared utilities
    # ------------------------------------------------------------------

    def is_empty_search_result(self, tool_content: str) -> bool:
        """Return True when search result indicates no useful results."""
        lower = (tool_content or "").lower()
        return any(marker in lower for marker in _EMPTY_MARKERS)

    def is_relevant_to_question(
        self, tool_content: str, question: str
    ) -> bool:
        """Return True when results actually address the question."""
        from airunner_services.llm.managers.concerns.relevance_check import (
            check_relevance,
        )
        return check_relevance(
            tool_content,
            question,
            self._get_fast_model(),
            self._owner.logger,
        )

    # ------------------------------------------------------------------
    # Model / tool resolution
    # ------------------------------------------------------------------

    def _get_fast_model(self) -> Optional[Any]:
        """Return the cheap fast model for classification."""
        specialized = getattr(
            self._owner, "_specialized_chat_models", {}
        )
        return (
            specialized.get("TOOL_CLASSIFICATION")
            or getattr(self._owner, "_original_chat_model", None)
            or getattr(self._owner, "_chat_model", None)
        )

    def _bound_tool_names(self) -> frozenset[str]:
        """Return the set of tool names currently bound to the workflow."""
        tools = getattr(self._owner, "_tools", []) or []
        return frozenset(
            getattr(t, "name", "") for t in tools
            if getattr(t, "name", None)
        )

    # ------------------------------------------------------------------
    # Tool message construction
    # ------------------------------------------------------------------

    def _make_tool_call_message(
        self, tool_name: str, args: Dict[str, Any]
    ) -> AIMessage:
        """Build a synthetic AIMessage containing one tool call."""
        return AIMessage(
            content="",
            tool_calls=[{
                "name": tool_name,
                "args": args,
                "id": f"gate_{uuid.uuid4().hex[:8]}",
                "type": "tool_call",
            }],
        )

    # ------------------------------------------------------------------
    # Context extraction
    # ------------------------------------------------------------------

    def _conversation_context(
        self, messages: List[BaseMessage]
    ) -> str:
        """Return the last 2 exchanges (4 msgs) as brief context text."""
        pairs: List[str] = []
        skipped_current = False
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage) and not skipped_current:
                skipped_current = True
                continue
            if msg.__class__.__name__ == "ToolMessage":
                continue
            if isinstance(msg, AIMessage) and getattr(
                msg, "tool_calls", None
            ):
                continue
            if isinstance(msg, HumanMessage):
                text = str(msg.content or "")[:120].replace("\n", " ")
                pairs.append(f"User: {text}")
            elif isinstance(msg, AIMessage):
                text = str(msg.content or "")[:120].replace("\n", " ")
                pairs.append(f"Assistant: {text}")
            if len(pairs) >= 4:
                break
        if not pairs:
            return ""
        return "\n".join(reversed(pairs))

    @staticmethod
    def _reset_turn_caches() -> None:
        """Clear per-turn caches before each new generation.

        Resets both the knowledge record dedup cache and the grounding
        source accumulator so each turn starts with a clean slate.
        """
        from airunner_services.llm.tools.grounding_tools_helpers import (
            clear_grounding_sources,
        )
        from airunner_services.llm.tools.knowledge_tools.record import (
            clear_turn_cache as clear_record_cache,
        )

        clear_grounding_sources()
        clear_record_cache()

    @staticmethod
    def _last_human_text(messages: List[BaseMessage]) -> str:
        """Return the text of the most recent HumanMessage."""
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                content = msg.content
                if isinstance(content, str):
                    return content
        return ""
