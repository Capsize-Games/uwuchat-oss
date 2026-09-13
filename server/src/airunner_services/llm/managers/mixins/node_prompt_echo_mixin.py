"""Echo-detection mixin for prompt assembly.

Extracted from node_prompt_assembly_helper.py to keep under 250 lines.
"""

from __future__ import annotations

from typing import Any, Dict, List

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

_ECHO_CORRECTION_MESSAGE = (
    "Your previous response was rejected because it"
    " restated the user's words without adding"
    " anything. Write a reply that contains zero"
    " phrases from the user's message and adds new"
    " information, a concrete opinion, or a follow-up"
    " that advances the conversation."
)


class NodePromptEchoMixin:
    """Echo detection and retry for model responses."""

    def _check_echo_and_retry(
        self,
        response: AIMessage,
        prompt: Any,
        state: Dict[str, Any],
        generation_kwargs: Dict[str, Any],
    ) -> AIMessage:
        """Retry with echo correction if the response echoes the user."""
        response_text = str(getattr(response, "content", "") or "")
        if not response_text.strip():
            return response
        user_text = self._get_last_user_message(state["messages"])
        if not user_text:
            return response
        import airunner_services.llm.managers.echo_detector as _ed
        ratio = _ed.echo_ratio(user_text, response_text)
        word_count = len(response_text.split())
        if ratio <= 0.45 or word_count >= 120:
            return response
        self._owner.logger.warning(
            "[ECHO] Response echoes user input "
            "(ratio=%.2f); retrying with correction",
            ratio,
        )
        return self._retry_with_echo_correction(
            prompt, generation_kwargs
        )

    def _retry_with_echo_correction(
        self,
        prompt: Any,
        generation_kwargs: Dict[str, Any],
    ) -> AIMessage:
        """Re-invoke model with echo-correction message appended."""
        prompt_msgs = (
            prompt.to_messages()
            if hasattr(prompt, "to_messages")
            else list(prompt)
        )
        retry_msgs = list(prompt_msgs) + [
            HumanMessage(content=_ECHO_CORRECTION_MESSAGE)
        ]
        return self._ensure_response(
            self._owner._get_response_generation_helper().generate_response(
                retry_msgs, generation_kwargs
            )
        )

    @staticmethod
    def _get_last_user_message(messages: List[BaseMessage]) -> str:
        """Return the text content of the most recent HumanMessage."""
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                content = msg.content
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    parts: list[str] = []
                    for block in content:
                        if (
                            isinstance(block, dict)
                            and block.get("type") == "text"
                        ):
                            parts.append(
                                str(block.get("text", ""))
                            )
                    return " ".join(parts)
        return ""
