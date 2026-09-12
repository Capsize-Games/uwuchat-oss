"""Time-gap simulation — generates a catch-up narrative after long absences."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from airunner_services.contract_enums import ModelService

logger = logging.getLogger(__name__)

GAP_NARRATIVE_MIN_HOURS: float = 4.0

_GAP_PROMPT = (
    "A user has been away for {elapsed}.\n"
    "CHARACTER: {archetype} — {name}\n"
    "LAST KNOWN STATE: {prev_state}\n"
    "WORLD EVENTS DURING ABSENCE: {world_events}\n\n"
    "Write a first-person catch-up message the character would send when the "
    "user returns. It should:\n"
    "- Reference what happened to them during the absence (specific, concrete)\n"
    "- Reflect the character's current emotional state\n"
    "- Be in the character's voice — not a generic update\n"
    "- Be 1-3 sentences. No 'welcome back' clichés.\n\n"
    "Then return ONLY a JSON object:\n"
    '{{"narrative": "the catch-up message", '
    '"updated_state": {{"situation": "...", "emotional_weather": "...", '
    '"current_activity": "..."}}}}\n\n'
    "Keep updated_state consistent with the elapsed time and world events."
)


def _elapsed_label(hours: float) -> str:
    """Return a human-friendly elapsed time string."""
    if hours < 2:
        return "a few hours"
    if hours < 24:
        return f"{int(hours)} hours"
    days = int(hours / 24)
    if days == 1:
        return "a day"
    if days < 7:
        return f"{days} days"
    weeks = int(days / 7)
    return f"{weeks} week{'s' if weeks > 1 else ''}"


def _parse_result(raw: str) -> Optional[dict]:
    """Extract JSON from LLM response."""
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start == -1 or end == 0:
            return None
        return json.loads(raw[start:end])
    except Exception:
        return None


class TimeGapEngine:
    """Generates a time-gap narrative when the user returns after an absence."""

    def __init__(self, app: Any) -> None:
        self._app = app

    def maybe_simulate(
        self, chatbot: Any, elapsed_hours: float
    ) -> Optional[str]:
        """Return a catch-up narrative if the gap is large enough."""
        if elapsed_hours < GAP_NARRATIVE_MIN_HOURS:
            return None
        return self._generate(chatbot, elapsed_hours)

    def _generate(
        self, chatbot: Any, elapsed_hours: float
    ) -> Optional[str]:
        """Call LLM to produce a time-gap narrative."""
        core = chatbot.identity_core or {}
        archetype = core.get("archetype", chatbot.botname)
        prev_state = chatbot.inner_state or {}
        world_events = []
        prompt = _GAP_PROMPT.format(
            elapsed=_elapsed_label(elapsed_hours),
            name=chatbot.botname,
            archetype=archetype,
            prev_state=json.dumps(prev_state, ensure_ascii=False),
            world_events=", ".join(world_events) if world_events else "none",
        )
        raw = self._call_llm(prompt)
        if not raw:
            return None
        result = _parse_result(raw)
        if not result:
            return None
        if result.get("updated_state"):
            self._merge_state(chatbot, result["updated_state"])
        return result.get("narrative")

    def _merge_state(self, chatbot: Any, updates: dict) -> None:
        """Merge partial state updates into the chatbot's inner_state."""
        try:
            from airunner_services.database.models.chatbot import Chatbot
            current = dict(chatbot.inner_state or {})
            current.update(
                {k: v for k, v in updates.items() if v is not None}
            )
            Chatbot.objects.update(chatbot.id, inner_state=current)
        except Exception:
            logger.exception(
                "TimeGapEngine state merge failed for chatbot %s", chatbot.id
            )

    def _call_llm(self, prompt: str) -> str:
        """Invoke the LLM runtime."""
        from airunner_services.runtimes.contracts import (
            ChatMessage as Msg,
            LLMInvocationRequest,
            MessageRole,
            RuntimeAction,
            RuntimeKind,
        )
        from airunner_services.ipc.messages import (
            EnvelopeStatus,
            RequestEnvelope,
        )
        try:
            registry = getattr(
                getattr(self._app, "state", None), "runtime_registry", None
            )
            if registry is None:
                return ""
            client = registry.resolve(
                RuntimeKind.LLM, provider=ModelService.LOCAL.value
            )
            msgs = [Msg(role=MessageRole.USER, content=prompt)]
            inv = LLMInvocationRequest(
                messages=msgs,
                metadata={"stateless": True},
                temperature=0.75,
                max_tokens=300,
            )
            env = RequestEnvelope(
                runtime=RuntimeKind.LLM,
                action=RuntimeAction.INVOKE,
                provider=ModelService.LOCAL.value,
                payload=inv.model_dump(),
            )
            resp = client.invoke(env)
            if resp.status is not EnvelopeStatus.SUCCEEDED:
                return ""
            return str(resp.payload.get("content", ""))
        except Exception:
            logger.exception("TimeGapEngine LLM call failed")
            return ""
