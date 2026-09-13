"""Inner state updater — updates a chatbot's living state document."""

from __future__ import annotations

import datetime
import json
import logging
from typing import Any, Dict, Optional

from airunner_services.contract_enums import ModelService

logger = logging.getLogger(__name__)

_DEFAULT_STATE: Dict[str, Any] = {
    "situation": "Going about my day",
    "body": "Feeling fine",
    "emotional_weather": "Calm and present",
    "preoccupations": [],
    "needs": "Nothing in particular",
    "recent_social": "No recent interactions",
    "current_activity": "Resting",
    "schedule_context": "Free time",
    "relationship_notes": {},
}

_UPDATE_PROMPT = (
    "You are updating the inner state of a character.\n"
    "IDENTITY: {archetype} — {occupation}\n"
    "SPECIES: {species}\n"
    "PREVIOUS STATE: {prev_state}\n"
    "ELAPSED TIME: {elapsed}\n"
    "EVENTS SINCE LAST UPDATE: {events}\n"
    "{occupation_context_line}"
    "INERTIA RULE: Core nature never changes between ticks. "
    "Dramatic mood shifts require specific triggering events. "
    "Without meaningful events, emotional_weather must shift only "
    "subtly from the previous value — one step, not a reversal. "
    "Variance is normal; whiplash is not.\n"
    "{species_body_hint}"
    "Return ONLY a JSON object with the same keys as PREVIOUS STATE, "
    "updated to reflect the passage of time. "
    "Present tense, specific and concrete."
)


_SPECIES_BODY_HINTS: dict[str, str] = {
    "human": "",
    "kemonomimi": (
        "BODY NOTE: ears and tail position reflect emotional state. "
        "Include in body field.\n"
    ),
    "anthro": (
        "BODY NOTE: non-human anatomy — fur, tail, claws etc. "
        "Reflect species physiology in body field.\n"
    ),
    "android": (
        "BODY NOTE: synthetic body — charge level, thermal state, "
        "sensor readings may appear in body field.\n"
    ),
    "spirit": (
        "BODY NOTE: incorporeal or semi-corporeal — "
        "ambient energy, manifestation density in body field.\n"
    ),
}


def _species_body_hint(chatbot: Any) -> str:
    """Return species-specific body state guidance."""
    species = (chatbot.species_data or {}).get("type", "human")
    return _SPECIES_BODY_HINTS.get(species, "")


def _build_prompt(
    chatbot: Any,
    prev_state: Dict[str, Any],
    elapsed: str,
    events: list,
    occupation_context: str = "",
) -> str:
    """Assemble the inner state update prompt."""
    core = chatbot.identity_core or {}
    archetype = core.get("archetype", chatbot.botname)
    occupation = (chatbot.attributes or {}).get("occupation", "unknown")
    species = (chatbot.species_data or {}).get("type", "human")
    occ_line = (
        f"SCHEDULE CONTEXT: {occupation_context}\n"
        if occupation_context else ""
    )
    return _UPDATE_PROMPT.format(
        archetype=archetype,
        occupation=occupation,
        species=species,
        prev_state=json.dumps(prev_state, ensure_ascii=False),
        elapsed=elapsed,
        events=json.dumps(events) if events else "none",
        occupation_context_line=occ_line,
        species_body_hint=_species_body_hint(chatbot),
    )


def _elapsed_str(last_tick: Optional[datetime.datetime]) -> str:
    """Return human-readable elapsed time since last tick."""
    if last_tick is None:
        return "unknown (first tick)"
    delta = datetime.datetime.utcnow() - last_tick
    hours = int(delta.total_seconds() // 3600)
    if hours < 1:
        return "less than an hour"
    return f"{hours} hour{'s' if hours != 1 else ''}"


def _parse_state(raw: str) -> Optional[Dict[str, Any]]:
    """Extract JSON dict from LLM response."""
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start == -1 or end == 0:
            return None
        return json.loads(raw[start:end])
    except Exception:
        return None


class InnerStateUpdater:
    """Updates a chatbot's inner_state document via LLM."""

    def __init__(self, app: Any) -> None:
        self._app = app

    def update(
        self,
        chatbot: Any,
        occupation_context: str = "",
    ) -> Optional[Dict[str, Any]]:
        """Generate and return an updated inner state dict."""
        prev = chatbot.inner_state or dict(_DEFAULT_STATE)
        elapsed = _elapsed_str(chatbot.last_tick_at)
        events = self._world_events(chatbot)
        prompt = _build_prompt(
            chatbot, prev, elapsed, events, occupation_context
        )
        raw = self._call_llm(prompt)
        if not raw:
            return None
        parsed = _parse_state(raw)
        if parsed is None:
            logger.warning(
                "InnerState parse failed for chatbot %s", chatbot.id
            )
            return None
        return parsed

    def _world_events(self, chatbot: Any) -> list:
        """Return relevant world event titles for this chatbot."""
        del chatbot
        return []

    def _call_llm(self, prompt: str) -> str:
        """Invoke LLM with the inner state update prompt."""
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
                max_tokens=400,
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
            logger.exception("InnerStateUpdater LLM call failed")
            return ""
