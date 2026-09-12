"""Identity core generator — builds the permanent character record."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from airunner_services.contract_enums import ModelService

logger = logging.getLogger(__name__)

_GEN_PROMPT = (
    "You are building a permanent identity record for an AI character.\n"
    "NAME: {name}\n"
    "PERSONALITY: {personality}\n"
    "BACKSTORY: {backstory}\n"
    "SPECIES: {species}\n"
    "OCCUPATION: {occupation}\n"
    "LOCATION: {location}\n\n"
    "Return ONLY a JSON object with these exact keys:\n"
    '{{\n'
    '  "archetype": "one-sentence essence of who this character is",\n'
    '  "background": {{\n'
    '    "schedule_archetype": "e.g. night owl creative / early riser working class",\n'
    '    "worldview": "brief worldview statement",\n'
    '    "formative_events": ["event 1", "event 2", "event 3"]\n'
    '  }},\n'
    '  "voice": {{\n'
    '    "vocabulary_level": 1-5,\n'
    '    "structure": "e.g. terse declarative / rambling associative",\n'
    '    "humor": "e.g. bone-dry deadpan or null",\n'
    '    "quirks": ["quirk 1", "quirk 2"],\n'
    '    "style_anchors": [\n'
    '      "verbatim example message 1",\n'
    '      "verbatim example message 2",\n'
    '      "verbatim example message 3"\n'
    '    ]\n'
    '  }},\n'
    '  "beliefs": {{\n'
    '    "cultural_values": ["value 1", "value 2", "value 3"],\n'
    '    "positions": {{\n'
    '      "topic name": "1-2 sentence position this character holds"\n'
    '    }},\n'
    '    "sensitivities": ["thing that makes them uncomfortable 1", "thing 2"]\n'
    '  }}\n'
    '}}\n\n'
    "Be specific and concrete. Formative events shape behavior but are "
    "never revealed directly. Style anchors must sound exactly like this "
    "character would text a friend — not like an AI assistant. "
    "Beliefs must reflect this character's specific background, not generic values."
)


def _build_prompt(chatbot: Any) -> str:
    """Assemble the identity core generation prompt."""
    attrs = chatbot.attributes or {}
    species = (chatbot.species_data or {}).get("type", "human")
    subtype = (chatbot.species_data or {}).get("subtype", "")
    species_label = f"{species}/{subtype}" if subtype else species
    loc = chatbot.location or {}
    loc_str = ", ".join(
        str(v) for v in [loc.get("city"), loc.get("country")] if v
    ) or "unknown"
    return _GEN_PROMPT.format(
        name=chatbot.botname or chatbot.name,
        personality=chatbot.bot_personality or "",
        backstory=chatbot.backstory or "",
        species=species_label,
        occupation=attrs.get("occupation", "unknown"),
        location=loc_str,
    )


def _parse_core(raw: str) -> Optional[Dict]:
    """Extract JSON from LLM response."""
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start == -1 or end == 0:
            return None
        return json.loads(raw[start:end])
    except Exception:
        return None


def _style_anchors(core: Dict) -> List[str]:
    """Return style anchors from a parsed identity core."""
    return core.get("voice", {}).get("style_anchors", [])


class IdentityCoreGenerator:
    """Generates and persists the permanent identity core for a chatbot."""

    def __init__(self, app: Any) -> None:
        self._app = app

    def generate(self, chatbot: Any) -> Optional[Dict]:
        """Generate identity core and persist it. Returns the core dict."""
        prompt = _build_prompt(chatbot)
        raw = self._call_llm(prompt)
        if not raw:
            return None
        core = _parse_core(raw)
        if core is None:
            logger.warning(
                "IdentityCore parse failed for chatbot %s", chatbot.id
            )
            return None
        anchors = _style_anchors(core)
        if not anchors:
            logger.warning(
                "IdentityCore missing style_anchors for chatbot %s",
                chatbot.id,
            )
        self._persist(chatbot.id, core)
        return core

    def _persist(self, chatbot_id: int, core: Dict) -> None:
        """Store the identity core on the chatbot record."""
        try:
            from airunner_services.database.models.chatbot import Chatbot
            Chatbot.objects.update(chatbot_id, identity_core=core)
        except Exception:
            logger.exception(
                "Failed to persist identity_core for chatbot %s", chatbot_id
            )

    def _call_llm(self, prompt: str) -> str:
        """Call the LLM runtime to generate the identity core JSON."""
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
                temperature=0.8,
                max_tokens=800,
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
            logger.exception("IdentityCoreGenerator LLM call failed")
            return ""
