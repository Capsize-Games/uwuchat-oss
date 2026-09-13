"""Two-pass response validator for roleplay-mode characters.

Pass 1: generate silently into a buffer.
Validation: cheap LLM checks whether the response violates the
            character's knowledge horizon.
Pass 2 (FAIL only): re-generate with a correction note injected
                    into the prompt, streamed directly to the client
                    without a second validation round.
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from airunner_services.data.tenant import get_tenant_key
from airunner_services.llm.token_usage import record_background_usage

from airunner_services.conf.model_settings import META_LLAMA_INSTRUCT_MODEL

logger = logging.getLogger(__name__)

_VALIDATION_PROMPT = (
    "Character: {name} ({species})\n"
    "This character only knows what their species directly experiences:"
    " habitat, instincts, immediate sensory world.\n"
    "They have no access to human knowledge, culture, or technology.\n\n"
    "Response to check:\n{response}\n\n"
    "Does this response draw on knowledge the character could not have?\n"
    "Reply ONLY with one of:\n"
    "PASS\n"
    "FAIL: [quote the specific phrase that violates the horizon]"
)

_CORRECTION_NOTE = (
    "[Internal correction: your previous draft contained knowledge your"
    " character does not have: {violation}. Write a new response staying"
    " entirely inside your direct sensory world."
    " Do not reference this correction.]"
)


class TwoPassResponseGenerator:
    """Buffer pass 1, validate, then replay or re-generate."""

    def __init__(self, owner, streaming_helper) -> None:
        self._owner = owner
        self._streaming = streaming_helper

    def generate(
        self,
        prompt: List[BaseMessage],
        generation_kwargs: dict,
    ) -> Optional[AIMessage]:
        """Run pass 1 buffered, validate, pass through or correct."""
        if not self._should_validate():
            return self._streaming.generate_streaming_response(
                prompt, generation_kwargs
            )
        buffer: list[str] = []
        original_cb = getattr(self._owner, "_token_callback", None)
        self._owner._token_callback = buffer.append
        try:
            first_pass = self._streaming.generate_streaming_response(
                prompt, generation_kwargs
            )
        finally:
            self._owner._token_callback = original_cb

        if not first_pass:
            return first_pass
        if getattr(first_pass, "tool_calls", None):
            _replay(original_cb, buffer)
            return first_pass

        violation = self._validate("".join(buffer))
        if not violation:
            logger.debug("[VALIDATOR] PASS")
            _replay(original_cb, buffer)
            return first_pass

        logger.debug("[VALIDATOR] FAIL — %s", violation[:120])
        corrected = _inject_correction(prompt, violation)
        return self._streaming.generate_streaming_response(
            corrected, generation_kwargs
        )

    def _should_validate(self) -> bool:
        try:
            from airunner_services.llm.managers.prompt_builder.identity_parts import (
                _is_rp_mode,
            )
            if not _is_rp_mode(self._owner):
                return False
            chatbot = getattr(self._owner, "chatbot", None)
            if not chatbot:
                return False
            return (
                getattr(chatbot, "knowledge_mode", "omniscient")
                == "roleplay"
            )
        except Exception:
            return False

    def _validate(self, text: str) -> Optional[str]:
        """Return violation string or None (PASS)."""
        from airunner_services.llm.pipeline_loader import (
            pipeline_config,
            is_enabled,
        )
        if not is_enabled("NODE_VALIDATOR"):
            return None
        score = getattr(self._owner, "_complexity_score", 0.0)
        if score < pipeline_config("NODE_VALIDATOR").get(
            "min_complexity", 0.0
        ):
            return None
        if len(text.strip()) < 10:
            return None
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            return None
        chatbot = getattr(self._owner, "chatbot", None)
        sd = getattr(chatbot, "species_data", None) or {}
        name = (getattr(chatbot, "botname", None) or "character").strip()
        species = sd.get("subtype") or sd.get("type") or "non-human"
        try:
            from langchain_core.messages import HumanMessage as HM
            from airunner_services.cloud.llm.model_builders import (
                create_openrouter_model,
            )
            from airunner_services.cloud.llm.completion_choke import (
                invoke_with_limiter,
            )
            cfg = pipeline_config("NODE_VALIDATOR")
            model = create_openrouter_model(
                api_key=api_key,
                model_name=cfg.get(
                    "model", META_LLAMA_INSTRUCT_MODEL
                ),
                temperature=cfg.get("temperature", 0.0),
                max_tokens=cfg.get("max_tokens", 60),
            )
            prompt_text = _VALIDATION_PROMPT.format(
                name=name,
                species=species,
                response=text[:600],
            )
            response = invoke_with_limiter(
                model,
                [HM(content=prompt_text)],
                priority="bulk",
            )
            record_background_usage(
                "NODE_VALIDATOR", cfg, response,
                tenant_key=get_tenant_key(),
                call_chain_id=getattr(
                    self._owner, "_call_chain_id", None
                ),
            )
            raw = str(getattr(response, "content", "")).strip()
            if raw.upper().startswith("PASS"):
                return None
            tail = raw[5:].strip() if raw.upper().startswith("FAIL:") else raw
            return tail or "unknown violation"
        except Exception as exc:
            from airunner_services.utils.network_retry import (
                is_transient_network_error,
                log_network_failure,
            )
            if is_transient_network_error(exc):
                log_network_failure(
                    logger, "Validation LLM call failed", exc
                )
            else:
                logger.error(
                    "Validation LLM call failed", exc_info=True
                )
            return None


def _replay(callback, buffer: list[str]) -> None:
    """Send buffered tokens to the client callback."""
    if not callback:
        return
    for tok in buffer:
        try:
            callback(tok)
        except Exception:
            pass


def _inject_correction(
    prompt: List[BaseMessage], violation: str
) -> List[BaseMessage]:
    """Append a correction note to the last human message."""
    note = _CORRECTION_NOTE.format(violation=violation[:200])
    result = list(prompt)
    for i in range(len(result) - 1, -1, -1):
        if isinstance(result[i], HumanMessage):
            orig = getattr(result[i], "content", "") or ""
            result[i] = HumanMessage(content=f"{orig}\n\n{note}")
            return result
    result.append(HumanMessage(content=note))
    return result
