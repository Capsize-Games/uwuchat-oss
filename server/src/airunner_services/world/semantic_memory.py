"""Semantic memory — extracts and indexes facts from session conversations."""

from __future__ import annotations

import json
import logging
from typing import Any

from airunner_services.contract_enums import ModelService

logger = logging.getLogger(__name__)

_EXTRACT_PROMPT = (
    "Extract 3-5 specific facts the user revealed about themselves from this"
    " conversation. Only include things the USER said, not the AI character.\n"
    "CONVERSATION:\n{messages}\n\n"
    "Return ONLY a JSON array of fact strings:\n"
    '["fact 1", "fact 2", "fact 3"]\n\n'
    "Facts must be specific. 'User likes coffee' is too vague."
    " 'User is a night-shift nurse in Chicago' is good."
    " Return [] if no clear facts emerge."
)


def _build_message_text(messages: list[dict]) -> str:
    """Format messages as USER:/ASSISTANT: pairs, truncated."""
    lines = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        role = m.get("role", "")
        content = str(m.get("content", ""))[:300]
        if role in ("user", "assistant"):
            lines.append(f"{role.upper()}: {content}")
    return "\n".join(lines[:30])


def _parse_facts(raw: str) -> list[str]:
    """Extract JSON array of facts from LLM response."""
    try:
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start == -1 or end == 0:
            return []
        result = json.loads(raw[start:end])
        return [str(f) for f in result if isinstance(f, str) and f.strip()]
    except Exception:
        return []


def _store_fact(chatbot_id: int, fact: str) -> None:
    """Store one extracted fact in the knowledge_facts table."""
    try:
        from airunner_services.knowledge import get_knowledge_base
        from airunner_services.knowledge_context import (
            set_knowledge_chatbot_id,
        )

        set_knowledge_chatbot_id(chatbot_id)
        get_knowledge_base().add_fact(fact)
    except Exception:
        logger.exception(
            "SemanticMemory store_fact failed for chatbot %s", chatbot_id
        )


class SemanticMemoryExtractor:
    """Extracts user facts from completed sessions into knowledge_facts."""

    def __init__(self, app: Any) -> None:
        self._app = app

    def extract(self, session_id: int, chatbot_id: int) -> None:
        """Pull facts from session and store them."""
        messages = self._load_messages(session_id)
        if not messages:
            return
        msg_text = _build_message_text(messages)
        if not msg_text.strip():
            return
        raw = self._call_llm(msg_text)
        facts = _parse_facts(raw)
        for fact in facts[:5]:
            _store_fact(chatbot_id, fact)
        if facts:
            logger.info(
                "SemanticMemory extracted %d facts for chatbot %s",
                len(facts), chatbot_id,
            )

    def _load_messages(self, session_id: int) -> list[dict]:
        """Return all messages from conversations in this session."""
        try:
            from airunner_services.database.models.conversation import (
                Conversation,
            )
            convs = (
                Conversation.objects.query()
                .filter(Conversation.session_id == session_id)
                .all()
            )
            msgs = []
            for conv in convs:
                msgs.extend(getattr(conv, "value", None) or [])
            return msgs
        except Exception:
            return []

    def _call_llm(self, msg_text: str) -> str:
        """Call LLM to extract facts."""
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
            prompt = _EXTRACT_PROMPT.format(messages=msg_text)
            msgs = [Msg(role=MessageRole.USER, content=prompt)]
            inv = LLMInvocationRequest(
                messages=msgs,
                metadata={"stateless": True},
                temperature=0.3,
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
            logger.exception("SemanticMemory LLM call failed")
            return ""
