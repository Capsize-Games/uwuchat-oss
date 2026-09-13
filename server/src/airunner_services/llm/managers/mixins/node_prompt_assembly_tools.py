"""Tool instruction and memory helpers for NodePromptAssemblyHelper."""

from __future__ import annotations

import re
from typing import List

from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage


class NodePromptAssemblyToolsMixin:
    """Tool-instruction injection for prompt assembly."""

    _owner: any

    def should_include_tool_instructions(
        self,
        trimmed_messages: List[BaseMessage],
    ) -> bool:
        """Return whether tool instructions should be injected."""
        if not self._owner._tools or not trimmed_messages:
            return False
        last = trimmed_messages[-1]
        if last.__class__.__name__ != "HumanMessage":
            return True
        content = (getattr(last, "content", "") or "").strip().lower()
        if len(content) > 25:
            return True
        action_keywords = [
            "solve",
            "calculate",
            "search",
            "find",
            "create",
            "generate",
            "update",
            "schedule",
            "plot",
            "graph",
        ]
        if any(keyword in content for keyword in action_keywords):
            return True
        greeting_patterns = {
            "hello",
            "hi",
            "hey",
            "good morning",
            "good afternoon",
            "good evening",
            "thanks",
            "thank you",
            "ok",
            "okay",
            "yo",
        }
        normalized = re.sub(r"[!.?,]", "", content)
        return normalized not in greeting_patterns

    def escape_system_prompt(self) -> str:
        """Escape curly braces in the stored system prompt."""
        prompt_source = self._owner._system_prompt
        return prompt_source.replace("{", "{{").replace("}", "}}")

    def get_memory_context_for_prompt(self) -> str:
        """Return one best-effort memory context string for prompts."""
        try:
            from airunner_services.knowledge import get_knowledge_base

            knowledge_base = get_knowledge_base()
            context = knowledge_base.get_context(max_chars=2000)
            if context:
                self._owner.logger.info(
                    "[MEMORY] Injecting %s chars of memory context",
                    len(context),
                )
            return context
        except Exception as exc:
            self._owner.logger.debug(
                "[MEMORY] Failed to get memory context: %s",
                exc,
            )
            return ""

    def add_tool_instructions(self, system_prompt: str) -> str:
        """Add compact tool instructions when the active mode needs them."""
        if not self._owner._tools:
            return system_prompt
        system_prompt = self._inject_compact_tools(system_prompt)
        force_tool = getattr(self._owner, "_force_tool", None)
        if force_tool:
            system_prompt = self._inject_force_tool_instruction(
                system_prompt,
                force_tool,
            )
        return system_prompt

    def _inject_compact_tools(self, system_prompt: str) -> str:
        """Inject compact tool list for react mode."""
        tool_calling_mode = getattr(
            self._owner._chat_model,
            "tool_calling_mode",
            "react",
        )
        if tool_calling_mode != "react":
            return system_prompt
        compact_tools = self._owner._create_compact_tool_list()
        if not compact_tools:
            return system_prompt
        escaped = compact_tools.replace("{", "{{").replace("}", "}}")
        self._owner.logger.debug(
            "Tools (%s) bound via bind_tools() (mode: %s)",
            len(self._owner._tools),
            tool_calling_mode,
        )
        return f"{system_prompt}\n\n{escaped}"

    def _inject_force_tool_instruction(
        self,
        system_prompt: str,
        force_tool: str,
    ) -> str:
        """Append sequential-tool-execution instructions."""
        system_prompt += (
            "\n\n=== IMPORTANT: SEQUENTIAL TOOL EXECUTION REQUIRED ===\n"
            f"You MUST call the '{force_tool}' tool FIRST and ONLY this "
            "tool.\n"
            "DO NOT call multiple tools at once.\n"
            "Call ONE tool, wait for the result, then call the next tool.\n"
            "This is a WORKFLOW - each step depends on the previous "
            "result.\n"
            "=== END INSTRUCTION ===\n"
        )
        self._owner.logger.info(
            "[TOOL INSTRUCTIONS] Added sequential execution instruction "
            "for force_tool='%s'",
            force_tool,
        )
        return system_prompt

    def _get_trimmed_messages(self, messages: list) -> list:
        """Return trimmed or full messages depending on vision model."""
        chat_model = getattr(self._owner, "_chat_model", None)
        if chat_model and getattr(chat_model, "is_vision_model", False):
            return messages
        return self.trim_messages(messages)

    def trim_messages(self, messages: list) -> list:
        """Trim message history to fit the configured context window.

        The current turn's exchange (the most recent HumanMessage and
        everything that follows — tool calls, tool results) is never
        trimmed.  Only older history is eligible for removal.  This
        prevents the model from receiving an empty message list when
        the current turn's content alone exceeds the budget (e.g. a
        large search result with two tool-call cycles in one turn).
        """
        from langchain_core.messages import trim_messages

        if not messages:
            return messages
        current_turn, prior = _split_current_turn(messages)
        trimmed_prior = prior
        if prior:
            trimmed_prior = trim_messages(
                prior,
                max_tokens=self._owner._max_history_tokens,
                strategy="last",
                token_counter=self._owner._token_counter,
                include_system=True,
                allow_partial=False,
                start_on="human",
            )
        # Truncate oversized ToolMessage content in the live
        # current-turn messages so a single enormous result does
        # not blow the provider's context window on its own.
        from airunner_services.llm.managers.message_utils import (
            truncate_oversized_human_message,
            truncate_oversized_tool_messages,
        )
        truncate_oversized_tool_messages(current_turn, max_chars=4000)
        # Truncate an oversized HumanMessage in the current turn
        # so a user pasting a huge article or file doesn't send
        # uncapped token costs through the model.
        truncate_oversized_human_message(current_turn)
        result = list(trimmed_prior) + current_turn
        if messages and not result:
            self._owner.logger.error(
                "[TRIM] Non-empty input (%d messages) produced empty "
                "result — this should never happen",
                len(messages),
            )
        return result

    def _gather_conversation_context(
        self, current_msg_count: int = 0
    ) -> str:
        """Return recent-conversation context with a session-bridge prefix."""
        try:
            from airunner_services.conversations.recent_context_builder import (
                RecentConversationContextBuilder,
            )
            from airunner_services.conversations.session_bridge_builder import (
                SessionBridgeBuilder,
            )

            current_id = getattr(self._owner, "_conversation_id", None)
            chatbot = getattr(self._owner, "chatbot", None)
            chatbot_id = getattr(chatbot, "id", None) if chatbot else None

            bridge = SessionBridgeBuilder().build_bridge(
                chatbot_id, current_id, current_msg_count
            )
            raw = RecentConversationContextBuilder().build_context(
                current_id, chatbot_id
            )

            parts: list[str] = []
            if bridge:
                parts.append(bridge)
            if raw:
                parts.append(raw)

            combined = "\n\n".join(parts)
            if not combined:
                return ""
            return combined.replace("{", "{{").replace("}", "}}")
        except Exception as exc:
            self._owner.logger.debug(
                "[RECENT CTX] Context gather failed: %s",
                exc,
            )
            return ""

    def _get_rolling_summary(self) -> str:
        """Return rolling summary for the current session, or empty."""
        try:
            conv_id = getattr(self._owner, "_conversation_id", None)
            if not conv_id:
                return ""
            from airunner_services.database.models.conversation import (
                Conversation,
            )
            from airunner_services.database.models.chat_session import (
                ChatSession,
            )

            conv = Conversation.objects.get(conv_id)
            if conv is None:
                return ""
            session_id = getattr(conv, "session_id", None)
            if not session_id:
                return ""
            sess = ChatSession.objects.get(session_id)
            if sess is None:
                return ""
            return (getattr(sess, "rolling_summary", None) or "").strip()
        except Exception:
            return ""

    @staticmethod
    def _inject_context_into_human_turn(
        messages: List[BaseMessage],
        per_turn: str,
        knowledge_block: str,
        conversation_block: str,
    ) -> List[BaseMessage]:
        """Prepend all dynamic context to the last HumanMessage.

        Keeps the system prompt stable (and thus cacheable) while still
        giving the model the information it needs each turn.
        """
        parts: list[str] = []
        if per_turn:
            parts.append(per_turn)
        if knowledge_block:
            raw = knowledge_block.replace("{{", "{").replace("}}", "}")
            parts.append(raw)
        if conversation_block:
            raw = conversation_block.replace("{{", "{").replace("}}", "}")
            parts.append(f"## Recent Conversations\n{raw}")
        if not parts:
            return messages
        ctx = "\n\n".join(parts)
        for i in range(len(messages) - 1, -1, -1):
            if isinstance(messages[i], HumanMessage):
                original = messages[i].content
                if isinstance(original, list):
                    new_content = [
                        {"type": "text", "text": f"{ctx}\n\n---\n\n"},
                        *original,
                    ]
                else:
                    new_content = f"{ctx}\n\n---\n\n{original}"
                result = list(messages)
                result[i] = HumanMessage(content=new_content)
                return result
        return messages


def _split_current_turn(
    messages: list,
) -> tuple[list, list]:
    """Split *messages* into (current_turn, prior_history).

    The current turn is everything from the last HumanMessage onward.
    Prior history is everything before that.
    """
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].__class__.__name__ == "HumanMessage":
            return messages[i:], messages[:i]
    return list(messages), []


def _make_knowledge_adder(seen: set[str], lines: list[str]):
    """Return a closure that adds unique, escaped knowledge lines."""

    def _add(text: str) -> None:
        clean = text.strip().replace("{", "{{").replace("}", "}}")
        if clean and clean not in seen:
            seen.add(clean)
            lines.append(f"- {clean}")

    return _add


def _collect_pre_prompt(owner, add_fn) -> None:
    """Feed pre-prompt user-knowledge lines into *add_fn*."""
    pre = getattr(owner, "_pre_prompt_knowledge", "")
    for line in pre.splitlines():
        add_fn(line.lstrip("- "))


def _collect_pre_prompt_self(owner, add_fn) -> None:
    """Feed pre-prompt self-knowledge lines into *add_fn*."""
    pre = getattr(owner, "_pre_prompt_self_knowledge", "")
    for line in pre.splitlines():
        add_fn(line.lstrip("- "))


def _collect_tool_text(messages) -> str:
    """Collect recent tool-result text for a knowledge search query."""
    tool_texts: list[str] = []
    for msg in reversed(messages[-8:]):
        if isinstance(msg, ToolMessage):
            content = getattr(msg, "content", "") or ""
            if isinstance(content, list):
                content = " ".join(
                    (str(p) for p in content if isinstance(p, str)),
                )
            if content:
                tool_texts.append(content[:400])
            if len(tool_texts) >= 3:
                break
    return " ".join(tool_texts)
