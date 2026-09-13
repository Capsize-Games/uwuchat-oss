"""Text generation functionality for LLM models."""

from typing import Any, Dict, Optional

from airunner_services.contract_enums import LLMActionType
from airunner_services.llm.managers.mixins.generation_execution_support import (
    do_generate,
)
from airunner_services.llm.llm_request import LLMRequest
from airunner_services.llm.managers.mixins.generation_signal_support import (
    _send_signal,
    send_end_of_message,
)


def _usage_int(usage: dict, *keys: str) -> Optional[int]:
    """Return the first nonzero int for *keys*, or None."""
    for key in keys:
        value = int(usage.get(key, 0) or 0)
        if value:
            return value
    return None


class GenerationMixin:
    """Mixin for LLM text generation functionality."""

    async def _do_generate(
        self,
        prompt: str,
        action: LLMActionType,
        system_prompt: Optional[str] = None,
        llm_request: Optional[Any] = None,
        do_tts_reply: bool = True,
        extra_context: Optional[Dict[str, Dict[str, Any]]] = None,
        skip_tool_setup: bool = False,
    ) -> Dict[str, Any]:
        """Generate a response using the loaded LLM.

        Args:
            prompt: The input prompt
            action: The LLM action type
            system_prompt: Optional system prompt override
            llm_request: Optional LLM request object
            do_tts_reply: Whether to enable TTS reply
            extra_context: Optional extra context dictionary
            skip_tool_setup: If True, skip tool setup (already filtered)

        Returns:
            Dictionary with 'response' key containing generated text
        """
        return await do_generate(
            self,
            prompt,
            action,
            system_prompt,
            llm_request,
            do_tts_reply,
            extra_context,
            skip_tool_setup,
        )

    def _do_stateless_generate(
        self,
        prompt: str,
        system_prompt: Optional[str],
        llm_request: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Run a one-shot completion straight against the chat model.

        Bypasses the conversation/chatbot/workflow machinery entirely: no
        Conversation or Chatbot rows are created and nothing is persisted.
        The result is emitted through the same streamed-signal channel the
        runtime client collects from, so callers receive it identically to a
        normal generation.
        """
        from langchain_core.messages import HumanMessage, SystemMessage

        workflow_manager = getattr(self, "_workflow_manager", None)
        # Check for a STATELESS-routed model first; fall back to the
        # original (un-tooled) chat model so the one-shot completion
        # isn't influenced by tools bound to the agent's working model.
        chat_model = (
            getattr(self, "_specialized_chat_models", {}).get("STATELESS")
            or getattr(workflow_manager, "_original_chat_model", None)
            or getattr(workflow_manager, "_chat_model", None)
        )
        if chat_model is None:
            self.logger.error(
                "Stateless generate requested but no chat model is loaded"
            )
            send_end_of_message(self, llm_request, [0], [], None, None, None)
            return {"response": ""}

        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt or ""))

        # ---- PII masking: mask LangChain messages before LLM egress ----
        vault = getattr(self, "_pii_vault", None)
        if vault is not None:
            from airunner_services.llm.pii.masker import (
                mask_langchain_messages,
            )
            messages = mask_langchain_messages(messages, vault)
        # ---- end PII ----

        content = ""
        prompt_tokens = completion_tokens = total_tokens = None
        try:
            result = chat_model.invoke(messages)
            content = getattr(result, "content", None)
            if not isinstance(content, str):
                content = "" if content is None else str(content)
            # ---- PII restoration: restore placeholders in response ----
            if vault is not None and isinstance(content, str) and content:
                try:
                    from airunner_services.llm.pii.restorer import (
                        restore_text,
                    )
                    content = restore_text(content, vault)
                except Exception:
                    pass
            # ---- end PII ----
            # Thinking models (Qwen3, DeepSeek R1) may put the entire
            # response in reasoning_content with empty content.
            if not content.strip():
                ak = getattr(result, "additional_kwargs", {}) or {}
                reasoning = ak.get("reasoning_content") or ""
                if isinstance(reasoning, str) and "{" in reasoning:
                    content = reasoning
                    self.logger.debug(
                        "Stateless: content empty; using reasoning_content"
                    )
            # Surface real token counts so the runtime envelope metadata
            # carries them and stateless callers (e.g. character
            # generation) can record usage themselves.
            usage_meta = getattr(result, "usage_metadata", None) or {}
            prompt_tokens = _usage_int(
                usage_meta, "input_tokens", "prompt_tokens"
            )
            completion_tokens = _usage_int(
                usage_meta, "output_tokens", "completion_tokens"
            )
            total_tokens = _usage_int(usage_meta, "total_tokens")
        except Exception as exc:
            self.logger.error("Stateless generate failed: %s", exc)

        sequence_counter = [0]
        if content:
            sequence_counter[0] += 1
            _send_signal(
                self,
                llm_request,
                content,
                is_end_of_message=False,
                is_first_message=True,
                sequence_number=sequence_counter[0],
                message_type="assistant",
            )
        send_end_of_message(
            self,
            llm_request,
            sequence_counter,
            [],
            prompt_tokens,
            completion_tokens,
            total_tokens,
        )
        return {"response": content}

    def _send_final_message(
        self, llm_request: Optional[LLMRequest] = None
    ) -> None:
        """Send a signal indicating the end of a message stream.

        Args:
            llm_request: Optional LLM request object
        """
        executed_tools = []
        if hasattr(self, "_workflow_manager") and self._workflow_manager:
            executed_tools = self._workflow_manager.get_executed_tools()
        send_end_of_message(
            self,
            llm_request,
            [0],
            list(executed_tools or []),
            None,
            None,
            None,
        )
