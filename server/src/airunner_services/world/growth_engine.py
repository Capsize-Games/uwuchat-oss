"""Growth Engine — threshold-based identity evolution for UwUs."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from airunner_services.contract_enums import ModelService

logger = logging.getLogger(__name__)

EMOTIONAL_WEIGHT_THRESHOLD: float = 0.7
TOPIC_REPEAT_THRESHOLD: int = 3

_GROWTH_PROMPT = (
    "A character is experiencing meaningful change based on recent events.\n"
    "IDENTITY: {archetype}\n"
    "CURRENT FORMATIVE EVENTS: {formative_events}\n"
    "TRIGGERING SESSION SUMMARY: {summary}\n"
    "EMOTIONAL WEIGHT: {weight}\n\n"
    "This event was significant enough to leave a mark. Update the character's"
    " identity accordingly. Return ONLY a JSON object:\n"
    '{{\n'
    '  "new_formative_event": "one specific sentence about what happened",'
    ' max 20 words,\n'
    '  "revised_worldview": "updated worldview, or null if unchanged",\n'
    '  "new_interest": "a topic or skill that deepened, or null"\n'
    '}}\n\n'
    "Core personality never reverses. Growth is slow and earned."
)


def _should_grow(session) -> bool:
    """Return True if this session's weight crosses the growth threshold."""
    weight = getattr(session, "emotional_weight", None)
    return weight is not None and float(weight) >= EMOTIONAL_WEIGHT_THRESHOLD


def _build_prompt(chatbot: Any, session) -> str:
    """Build the growth engine prompt."""
    core = chatbot.identity_core or {}
    archetype = core.get("archetype", chatbot.botname)
    bg = core.get("background", {})
    events = bg.get("formative_events", [])
    summary = getattr(session, "episodic_summary", "") or ""
    weight = getattr(session, "emotional_weight", 0.0)
    return _GROWTH_PROMPT.format(
        archetype=archetype,
        formative_events=json.dumps(events, ensure_ascii=False),
        summary=summary,
        weight=weight,
    )


def _parse_growth(raw: str) -> Optional[dict]:
    """Extract JSON from LLM response."""
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start == -1 or end == 0:
            return None
        return json.loads(raw[start:end])
    except Exception:
        return None


def _apply_growth(chatbot: Any, growth: dict) -> dict:
    """Return an updated identity_core with growth applied."""
    core = dict(chatbot.identity_core or {})
    bg = dict(core.get("background", {}))
    events: list = list(bg.get("formative_events", []))

    new_event = growth.get("new_formative_event")
    if new_event and new_event not in events:
        events.append(new_event)
        if len(events) > 8:
            events = events[-8:]
        bg["formative_events"] = events

    revised = growth.get("revised_worldview")
    if revised:
        bg["worldview"] = revised

    new_interest = growth.get("new_interest")
    if new_interest:
        beliefs = dict(core.get("beliefs", {}))
        values: list = list(beliefs.get("cultural_values", []))
        if new_interest not in values:
            values.append(new_interest)
        beliefs["cultural_values"] = values
        core["beliefs"] = beliefs

    core["background"] = bg
    return core


class GrowthEngine:
    """Applies threshold-based identity evolution to a chatbot."""

    def __init__(self, app: Any) -> None:
        self._app = app

    def maybe_evolve(self, chatbot: Any) -> None:
        """Check recent cold sessions and apply growth if warranted."""
        try:
            from airunner_services.database.models.chat_session import (
                ChatSession,
            )
            sessions = (
                ChatSession.objects.query()
                .filter(
                    ChatSession.chatbot_id == chatbot.id,
                    ChatSession.summary_ready.is_(True),
                    ChatSession.episodic_summary.isnot(None),
                )
                .order_by(ChatSession.last_message_at.desc())
                .limit(3)
                .all()
            )
            for session in sessions:
                if _should_grow(session):
                    self._evolve(chatbot, session)
                    break
        except Exception:
            logger.exception(
                "GrowthEngine check failed for chatbot %s", chatbot.id
            )

    def _evolve(self, chatbot: Any, session: Any) -> None:
        """Generate and apply one growth step."""
        prompt = _build_prompt(chatbot, session)
        raw = self._call_llm(prompt)
        if not raw:
            return
        growth = _parse_growth(raw)
        if not growth:
            logger.warning(
                "GrowthEngine parse failed for chatbot %s", chatbot.id
            )
            return
        updated_core = _apply_growth(chatbot, growth)
        try:
            from airunner_services.database.models.chatbot import Chatbot
            Chatbot.objects.update(chatbot.id, identity_core=updated_core)
            logger.info(
                "GrowthEngine applied to chatbot %s: %s",
                chatbot.id,
                growth.get("new_formative_event", ""),
            )
        except Exception:
            logger.exception(
                "GrowthEngine persist failed for chatbot %s", chatbot.id
            )

    def _call_llm(self, prompt: str) -> str:
        """Invoke the LLM runtime for growth evaluation."""
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
                temperature=0.7,
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
            logger.exception("GrowthEngine LLM call failed")
            return ""
