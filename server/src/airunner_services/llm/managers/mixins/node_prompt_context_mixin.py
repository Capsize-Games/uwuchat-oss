"""Knowledge-context and vision-prompt mixin.

Extracted from node_prompt_assembly_helper.py.  Contains knowledge-base
gathering and vision-model prompt assembly.
"""

from __future__ import annotations

from typing import List

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    SystemMessage,
)


class NodePromptContextMixin:
    """Gather knowledge context and build vision-model prompts."""

    def _gather_knowledge_context(
        self, messages: List[BaseMessage]
    ) -> str:
        """Return labeled bullet lists of user-facts and self-facts.

        When the system bot has omnipotent_knowledge enabled, facts
        from ALL non-blocked chatbots are searched instead of only
        the current chatbot's knowledge.
        """
        try:
            from airunner_services.knowledge import get_knowledge_base
            from airunner_services.knowledge_context import (
                set_knowledge_subject,
            )
            from airunner_services.llm.managers.mixins import (
                node_prompt_assembly_tools as npat,
            )

            kb = get_knowledge_base()
            query = npat._collect_tool_text(messages)

            chatbot = getattr(self._owner, "chatbot", None)
            omnipotent = bool(
                getattr(chatbot, "is_system_bot", False)
                and getattr(chatbot, "omnipotent_knowledge", False)
            )

            user_seen: set[str] = set()
            user_lines: list[str] = []
            user_add = npat._make_knowledge_adder(
                user_seen, user_lines
            )
            npat._collect_pre_prompt(self._owner, user_add)
            if query.strip():
                set_knowledge_subject("user")
                try:
                    search_fn = (
                        kb.search_omnipotent_rag
                        if omnipotent
                        else kb.search_rag
                    )
                    kwargs = {
                        "query": query,
                        "k": 4,
                        "agent": self._owner,
                    }
                    for text in search_fn(**kwargs):
                        user_add(text)
                finally:
                    set_knowledge_subject("user")

            self_seen: set[str] = set()
            self_lines: list[str] = []
            self_add = npat._make_knowledge_adder(
                self_seen, self_lines
            )
            npat._collect_pre_prompt_self(self._owner, self_add)
            if query.strip():
                set_knowledge_subject("self")
                try:
                    search_fn = (
                        kb.search_omnipotent_rag
                        if omnipotent
                        else kb.search_rag
                    )
                    kwargs = {
                        "query": query,
                        "k": 4,
                        "agent": self._owner,
                    }
                    for text in search_fn(**kwargs):
                        self_add(text)
                finally:
                    set_knowledge_subject("user")

            blocks: list[str] = []
            if user_lines:
                blocks.append(
                    "## What I know about you:\n"
                    + "\n".join(user_lines)
                )
            if self_lines:
                blocks.append(
                    "## Things I remember about myself:\n"
                    + "\n".join(self_lines)
                )
            return "\n\n".join(blocks)
        except Exception as exc:
            self._owner.logger.debug(
                "[KNOWLEDGE AUTO] Context gather failed: %s",
                exc,
            )
            return ""

    def _build_vision_prompt(
        self, trimmed_messages: List[BaseMessage]
    ):
        """Build one vision prompt while preserving multimodal data."""
        per_turn = getattr(self._owner, "_per_turn_context", "") or ""
        knowledge = self._gather_knowledge_context(trimmed_messages)
        conv = self._gather_conversation_context(
            len(trimmed_messages)
        )
        trimmed_messages = self._inject_context_into_human_turn(
            trimmed_messages, per_turn, knowledge, conv
        )
        system_prompt = self._build_augmented_system_prompt(
            trimmed_messages
        )
        merged = self._merge_consecutive_humans(
            [SystemMessage(content=system_prompt), *trimmed_messages]
        )
        self._log_vision_prompt_debug(merged)
        return merged

    def _build_augmented_system_prompt(
        self,
        trimmed_messages: List[BaseMessage],
    ) -> str:
        """Return the stable system prompt with tool instructions."""
        prompt = self.escape_system_prompt()
        prompt = self.add_tool_instructions(prompt)
        helper = self._owner._get_post_tool_instructions_helper()
        return helper.add_post_tool_instructions(
            prompt, trimmed_messages
        )

    def _merge_consecutive_humans(
        self,
        messages: List[BaseMessage],
    ) -> List[BaseMessage]:
        """Merge consecutive HumanMessages to preserve alternation."""
        result: List[BaseMessage] = []
        for msg in messages:
            if msg is None:
                self._owner.logger.warning(
                    "[VISION PROMPT] Skipping None message"
                )
                continue
            if (
                result
                and isinstance(msg, HumanMessage)
                and isinstance(result[-1], HumanMessage)
            ):
                self._merge_human_content(result[-1], msg)
                self._owner.logger.debug(
                    "[VISION PROMPT] Merged consecutive"
                    " HumanMessages"
                )
                continue
            result.append(msg)
        return result

    def _log_vision_prompt_debug(
        self,
        messages: List[BaseMessage],
    ) -> None:
        """Log vision prompt build statistics."""
        has_human = any(
            isinstance(m, HumanMessage) for m in messages
        )
        if not has_human:
            self._owner.logger.warning(
                "[VISION PROMPT] No HumanMessage; len=%s",
                len(messages),
            )
        else:
            self._owner.logger.debug(
                "[VISION PROMPT] count=%s (system + %s msgs)",
                len(messages),
                len(messages) - 1,
            )

    @staticmethod
    def _merge_human_content(
        target: HumanMessage, message: HumanMessage
    ) -> None:
        """Merge one human message into the previous human message."""
        current_content = target.content
        new_content = message.content
        if isinstance(current_content, list) and isinstance(
            new_content, list
        ):
            target.content = current_content + new_content
            return
        if isinstance(current_content, list):
            target.content = current_content + [new_content]
            return
        if isinstance(new_content, list):
            target.content = [current_content] + new_content
            return
        target.content = f"{current_content}\n{new_content}"
