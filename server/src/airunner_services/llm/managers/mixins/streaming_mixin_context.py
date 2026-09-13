"""Context binding and knowledge search helpers for StreamingMixin."""

from __future__ import annotations

import re

from langchain_core.messages import AIMessage

# Patterns that trigger an immediate auto-block before the LLM
# ever sees the message.  This prevents the LLM from producing
# repetitive "I can't engage with hate speech" refusals and
# instead gives the user a decisive block.
_ABUSE_RE = re.compile(
    r"\b(?:n[i1]gg[ae]r|f[a@]gg[o0]t|k[i1]ke|ch[i1]nk|sp[i1]c|"
    r"w[e3]tb[a@]ck|towelhead|sandn[i1]gg[ae]r|r[a@]ghead|"
    r"tr[a@]nny|sh[e3]male|h[o0]m[o0]|r[e3]t[a@]rd)\b",
    re.IGNORECASE,
)


class StreamingMixinContext:
    """Context binding, knowledge search, and mood attachment helpers."""

    logger: any
    _pre_prompt_knowledge: str

    def _search_knowledge_for_prompt(
        self, text: str, subject: str = "user"
    ) -> str:
        """Keyword-search the knowledge base and return matching facts.

        subject controls whether user-facts or self-facts are searched.
        The ContextVar is always reset to 'user' in the finally block.

        When the system bot has omnipotent_knowledge enabled, facts from
        ALL non-blocked chatbots are searched.
        """
        if not text or not text.strip():
            return ""
        try:
            from airunner_services.knowledge import get_knowledge_base
            from airunner_services.knowledge_context import (
                set_knowledge_subject,
            )

            set_knowledge_subject(subject)
            kb = get_knowledge_base()

            chatbot = getattr(self, "chatbot", None)
            omnipotent = bool(
                getattr(chatbot, "is_system_bot", False)
                and getattr(chatbot, "omnipotent_knowledge", False)
            )

            if omnipotent:
                facts = kb._search_facts_omnipotent(
                    text.strip(), limit=15,
                )
            else:
                facts = kb.search_facts(text.strip(), limit=6)

            if not facts:
                return ""
            return "\n".join(f"- {f.fact_text}" for f in facts if f.fact_text)
        except Exception as exc:
            self.logger.debug(
                "[KNOWLEDGE AUTO] Search failed (%s): %s", subject, exc
            )
            return ""
        finally:
            try:
                from airunner_services.knowledge_context import (
                    set_knowledge_subject,
                )

                set_knowledge_subject("user")
            except Exception:
                pass

    def _auto_learn_from_message(self, user_input: str) -> None:
        """Extract URLs and scrape them for immediate prompt injection."""
        from airunner_services.llm.url_extractor import (
            extract_and_store_urls,
        )

        chatbot = getattr(self, "chatbot", None)
        chatbot_id = getattr(chatbot, "id", None) if chatbot else None
        scraped = extract_and_store_urls(user_input, chatbot_id)
        if scraped:
            self._scraped_url_context = "\n\n".join(scraped)
        else:
            self._scraped_url_context = ""

    def _pre_search_knowledge(self, user_input: str) -> None:
        """Pre-prompt knowledge search — user facts and self-facts separately."""
        self._pre_prompt_knowledge = self._search_knowledge_for_prompt(
            user_input, subject="user"
        )
        self._pre_prompt_self_knowledge = self._search_knowledge_for_prompt(
            user_input, subject="self"
        )
        total = len(self._pre_prompt_knowledge) + len(
            self._pre_prompt_self_knowledge
        )
        if total:
            self.logger.info(
                "[KNOWLEDGE AUTO] Pre-prompt context: %s char(s)",
                total,
            )

    def _bind_mood_context(self) -> None:
        """Bind event sink + conversation_id into mood ContextVar."""
        try:
            from airunner_services.llm.tools.mood_tools import (
                set_mood_context,
            )
            from airunner_services.llm_workflow_events import (
                resolve_llm_workflow_event_sink,
            )

            chatbot = getattr(self, "chatbot", None)
            chatbot_id = getattr(chatbot, "id", None) if chatbot else None
            conv_id = getattr(self, "_conversation_id", None)
            self.logger.warning(
                "[MOOD DEBUG] _bind_mood_context conv_id=%s chatbot_id=%s",
                conv_id, chatbot_id,
            )
            set_mood_context(
                resolve_llm_workflow_event_sink(self),
                conv_id,
                chatbot_id=chatbot_id,
                request_id=getattr(self, "_current_request_id", None),
            )
        except Exception:
            self.logger.exception("[MOOD DEBUG] _bind_mood_context failed")

    def _bind_knowledge_context(self) -> None:
        """Bind chatbot_id into knowledge ContextVar for agent scoping."""
        try:
            from airunner_services.knowledge_context import (
                set_knowledge_chatbot_id,
            )

            chatbot = getattr(self, "chatbot", None)
            chatbot_id = getattr(chatbot, "id", None) if chatbot else None
            set_knowledge_chatbot_id(chatbot_id)
        except Exception:
            self.logger.error(
                "_bind_knowledge_context failed — "
                "knowledge ContextVar not set for this turn",
                exc_info=True,
            )

    def _bind_social_context(self) -> None:
        """Bind chatbot_id and event sink into social ContextVar for tools."""
        try:
            from airunner_services.llm.tools.social_tools import (
                set_social_context,
            )
            from airunner_services.llm_workflow_events import (
                resolve_llm_workflow_event_sink,
            )

            chatbot = getattr(self, "chatbot", None)
            chatbot_id = getattr(chatbot, "id", None) if chatbot else None
            event_sink = resolve_llm_workflow_event_sink(self)
            set_social_context(
                chatbot_id,
                request_id=getattr(self, "_current_request_id", None),
                event_sink=event_sink,
            )
            # Store on self so finalize_generation can emit social events
            self._event_sink = event_sink
        except Exception:
            self.logger.error(
                "_bind_social_context failed — "
                "social ContextVar not set for this turn",
                exc_info=True,
            )

    def _check_availability(
        self, user_input: str = ""
    ) -> "str | None":
        """Return an error string when this chatbot can't respond, else None.

        Checks: already blocked, offline, abuse/hate-speech in user_input.
        Uses get_chatbot() to always resolve the CURRENT chatbot — not
        the WorkflowManager's cached reference which is stale across
        chatbot switches.
        """
        from airunner_services.llm.get_chatbot import get_chatbot
        chatbot = get_chatbot()
        if chatbot is None:
            return None
        if getattr(chatbot, "is_deceased", False):
            name = getattr(chatbot, "botname", None) or "They"
            reason = getattr(chatbot, "death_reason", None) or ""
            msg = f"{name} has passed away."
            if reason:
                msg += f" {reason}"
            return msg
        if getattr(chatbot, "blocked_by_user", False):
            return None
        if getattr(chatbot, "has_blocked_user", False):
            name = getattr(chatbot, "botname", None) or "I"
            return f"{name} has blocked you and can't respond."
        if not getattr(chatbot, "is_online", True):
            return self._check_offline_status(chatbot)

        # Abuse detection: block immediately when the user sends
        # explicit slurs or hate speech.
        if user_input and _ABUSE_RE.search(user_input):
            cid = getattr(chatbot, "id", None)
            if cid is not None:
                from airunner_services.database.models.chatbot import (
                    Chatbot,
                )
                Chatbot.objects.update(
                    cid,
                    has_blocked_user=True,
                    block_reason="abuse detected in user message",
                )
                chatbot.has_blocked_user = True
                self.logger.info(
                    "Auto-blocked user via chatbot %s (abuse detection)",
                    cid,
                )
                name = getattr(chatbot, "botname", None) or "I"
                return (
                    f"{name} has blocked you for "
                    f"violating community standards."
                )
        return None

    def _run_preflight_guard(self, user_input: str) -> "str | None":
        """Run safety pre-flight and auto-block on HARD_BLOCK.

        Returns a visible guard message when the request is rejected,
        or None when it passes.
        """
        try:
            from airunner_services.llm.safety.preflight import (
                PreflightOutcome,
                run_preflight,
            )
            result = run_preflight(user_input)
            if result.outcome != PreflightOutcome.HARD_BLOCK:
                return None
            self.logger.warning(
                "Pre-flight HARD_BLOCK in stream — request rejected"
            )
            # Auto-block the user
            chatbot = getattr(self, "chatbot", None)
            if chatbot and not getattr(chatbot, "has_blocked_user", False):
                cid = getattr(chatbot, "id", None)
                if cid:
                    from airunner_services.database.models.chatbot import (
                        Chatbot,
                    )
                    Chatbot.objects.update(
                        cid,
                        has_blocked_user=True,
                        block_reason="preflight safety guard",
                    )
                    self.logger.info(
                        "Auto-blocked user via chatbot %s "
                        "(preflight HARD_BLOCK in stream)",
                        cid,
                    )
            name = getattr(chatbot, "botname", None) or "The character"
            return (
                f"{name} has blocked you for violating "
                f"community standards."
            )
        except Exception as exc:
            self.logger.debug("Preflight guard failed: %s", exc)
            return None

    @staticmethod
    def _check_offline_status(chatbot: object) -> "str | None":
        """Return offline message if still offline; auto-restore if expired."""
        from datetime import datetime, timezone

        offline_until = getattr(chatbot, "offline_until", None)
        if not offline_until:
            return None
        if isinstance(offline_until, str):
            offline_until = datetime.fromisoformat(offline_until)
        if offline_until.tzinfo is None:
            offline_until = offline_until.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) < offline_until:
            name = getattr(chatbot, "botname", None) or "I"
            return f"{name} is offline right now and will be back later."
        from airunner_services.database.models.chatbot import Chatbot
        Chatbot.objects.update(
            chatbot.id, is_online=True, offline_until=None
        )
        return None

    @staticmethod
    def _count_ai_messages(event: dict) -> int:
        """Count AIMessage instances in an event."""
        return sum(
            1 for msg in event["messages"] if isinstance(msg, AIMessage)
        )

    def _attach_mood(self, ai_message: AIMessage) -> None:
        """Attach current mood/emoji, strip tool-call text, persist mood."""
        current_mood = getattr(self, "_current_mood", "neutral")
        current_emoji = getattr(self, "_current_emoji", "😐")
        current_kaomoji = getattr(
            self, "_current_kaomoji", "(｡◕ᴗ◕｡)"
        )
        ai_message.additional_kwargs["bot_mood"] = current_mood
        ai_message.additional_kwargs["bot_mood_emoji"] = current_emoji
        ai_message.additional_kwargs["bot_mood_kaomoji"] = (
            current_kaomoji
        )
        # Strip tool-call text so it never reaches the message list
        import re
        _RE = re.compile(
            r"\b(?:update_mood|block_user)\s*\([^)]*\)"
        )
        ai_message.content = _RE.sub(
            "", ai_message.content or ""
        ).strip()
        # Messages are checkpointed before this method runs, so
        # bot_mood never makes it to the DB via the message itself.
        # Persist current_mood to conv.user_data here instead.
        self.logger.warning(
            "[MOOD DEBUG] _attach_mood current_mood=%r kaomoji=%r has_tool_calls=%s",
            current_mood, current_kaomoji,
            bool(getattr(ai_message, "tool_calls", None)),
        )
        if current_mood and current_mood != "neutral":
            self._persist_mood_to_conv_user_data(
                current_mood, current_emoji, current_kaomoji
            )

    def _persist_mood_to_conv_user_data(
        self,
        mood: str,
        emoji: str,
        kaomoji: str,
    ) -> None:
        """Write current mood into conv.user_data so reload works."""
        try:
            conv_id = getattr(self, "_conversation_id", None)
            self.logger.warning(
                "[MOOD DEBUG] _persist_mood_to_conv_user_data conv_id=%s "
                "mood=%r kaomoji=%r",
                conv_id, mood, kaomoji,
            )
            if not conv_id:
                return
            from airunner_services.database.models.conversation import (
                Conversation,
            )
            conv = Conversation.objects.get(conv_id)
            if conv is None:
                self.logger.warning(
                    "[MOOD DEBUG] _persist_mood_to_conv_user_data "
                    "conv NOT FOUND for id=%s", conv_id,
                )
                return
            ud = conv.user_data or {}
            ud["current_mood"] = {
                "mood": mood,
                "emoji": emoji,
                "kaomoji": kaomoji,
            }
            Conversation.objects.update(conv_id, user_data=ud)
            self.logger.warning(
                "[MOOD DEBUG] _persist_mood_to_conv_user_data SUCCESS "
                "conv_id=%s", conv_id,
            )
        except Exception as exc:
            self.logger.exception(
                "[MOOD DEBUG] _persist_mood_to_conv_user_data FAILED: %s",
                exc,
            )

    @staticmethod
    def _tag_if_thinking(ai_message: AIMessage) -> None:
        """Mark intermediate agentic-loop messages as thinking.

        When an AIMessage carries tool_calls it represents the model's
        intermediate reasoning — not the final response.  Tag it so
        the client can render a "thinking…" indicator.
        """
        if getattr(ai_message, "tool_calls", None):
            ai_message.additional_kwargs["is_thinking"] = True
