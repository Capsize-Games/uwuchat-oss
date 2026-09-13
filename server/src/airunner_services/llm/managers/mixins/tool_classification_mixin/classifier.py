"""LLM-assisted tool classification entry point."""

from __future__ import annotations

from airunner_services.llm.managers.mixins.tool_classification_mixin.heuristics import (
    _below_min_complexity,
    _looks_like_refusal,
)
from airunner_services.llm.utils.stream_debug import print_stream_debug


class ToolClassificationClassifierMixin:
    """Classify a prompt into tool categories using the active model."""

    def _classify_prompt_for_tools(
        self,
        prompt: str,
        allow_thinking: bool = True,
    ) -> list:
        """Use the active model to classify tool needs."""
        if _below_min_complexity(self, prompt):
            return []
        available_categories = [
            "research", "math", "image", "system", "recall",
            "knowledge", "code",
        ]
        prompt_directive = "" if allow_thinking else "/no_think\n"
        classification_prompt = (
            f"{prompt_directive}\n"
            "Classify which tool categories are needed to answer"
            " this user message.\n\n"
            f"Categories: {', '.join(available_categories)}\n\n"
            "Guidelines (pick the FIRST that applies):\n"
            '- "research": any message that mentions or asks about'
            " a real-world event, place, person, organization, show,"
            " news story, or cultural reference \u2014 even if phrased"
            " as a casual statement rather than a question, and even"
            " if it sounds like general knowledge."
            " Exclude weather/forecast/temperature conditions"
            " (those belong to \"system\")."
            " When in doubt, choose research.\n"
            '- "math": explicit calculation or unit conversion.\n'
            '- "image": user wants an image generated.\n'
            '- "system": calendar events, reminders, scheduling,'
            " anything the user wants remembered at a specific future"
            " time, the weather/forecast/temperature at any location,"
            " or an explicit request to post/send a message to"
            " Mattermost or a named Mattermost channel.\n"
            '- "recall": the user asks what you talked about before,'
            " on a specific day, or in a past session; asks you to"
            " search through prior conversation history for a specific"
            " exchange, topic, or detail; asks you to look up"
            " information from their synced email/inbox — anything"
            " requiring you to search past conversation transcripts"
            " or email data rather than answer from current context.\n"
            '- "knowledge": the user asks about a stored personal'
            " fact, detail, or preference about themselves (their"
            " name, relationships, family, job, health, hobbies,"
            " birthday, etc.) — anything the bot has previously"
            " recorded about the user via record_knowledge."
            " This is distinct from \"recall\" (which searches"
            " conversation transcripts); \"knowledge\" looks up"
            " discrete stored facts.\n"
            '- "code": the user explicitly asks to launch, start, or'
            " run a headlesscode/coding-agent session on one of their"
            " registered projects — a direct request to kick off"
            " automated dev work right now — OR asks the bot to do"
            " hands-on coding work on a registered project itself:"
            " run a shell command (git/gh/npm/build/test/scripts),"
            " read/write/edit a file, list files, search a project's"
            " code, or run its tests. Do NOT choose this for merely"
            " talking about code, debugging, or past dev work in the"
            " abstract (those are \"recall\"/\"knowledge\"/\"none\")"
            " — only an explicit launch/start/run request or an"
            " explicit hands-on command/file/search/test request.\n"
            '- "none": pure small talk, jokes, creative fiction, or'
            " personal opinions with no factual claims about the"
            " real world.\n\n"
            f'Message: "{prompt[:500]}"\n\n'
            'Reply with ONLY category names (comma-separated) or "none":'
        )

        try:
            if self._workflow_manager and hasattr(
                self._workflow_manager,
                "_original_chat_model",
            ):
                chat_model = self._get_classification_model()
                if not chat_model:
                    chat_model = self._workflow_manager._original_chat_model
                if chat_model:
                    original_thinking = getattr(
                        chat_model,
                        "enable_thinking",
                        True,
                    )
                    if hasattr(chat_model, "enable_thinking"):
                        chat_model.enable_thinking = allow_thinking

                    original_temp = getattr(chat_model, "temperature", 0.7)
                    if hasattr(chat_model, "temperature"):
                        chat_model.temperature = 0.1

                    original_tool_choice = getattr(
                        chat_model,
                        "tool_choice",
                        None,
                    )
                    if hasattr(chat_model, "tool_choice"):
                        chat_model.tool_choice = "none"

                    try:
                        if allow_thinking:
                            thinking_text, response_text = (
                                self._stream_classification_response(
                                    chat_model,
                                    classification_prompt,
                                    allow_thinking,
                                )
                            )
                        else:
                            thinking_text, response_text = (
                                self._invoke_classification_response(
                                    chat_model,
                                    classification_prompt,
                                )
                            )
                    finally:
                        if hasattr(chat_model, "enable_thinking"):
                            chat_model.enable_thinking = original_thinking
                        if hasattr(chat_model, "temperature"):
                            chat_model.temperature = original_temp
                        if hasattr(chat_model, "tool_choice"):
                            chat_model.tool_choice = original_tool_choice

                    print_stream_debug(
                        "tool_classification.response",
                        original_enable_thinking=original_thinking,
                        requested_enable_thinking=allow_thinking,
                        prompt_no_think=not allow_thinking,
                        content=response_text,
                        reasoning_content=thinking_text,
                    )

                    # Detect LLM safety-filter refusals so they don't
                    # leak into the conversation as the chatbot's reply.
                    if _looks_like_refusal(response_text):
                        self.logger.warning(
                            "Classification LLM refused: %r — "
                            "falling back to default categories",
                            response_text[:120],
                        )
                        return ["conversation", "chat", "mood"]

                    candidate_texts = self._classification_candidates(
                        response_text
                    )
                    candidate_text = (
                        candidate_texts[0] if candidate_texts else ""
                    )
                    self.logger.info(
                        "LLM classification response: %s",
                        candidate_text,
                    )
                    if candidate_text == "none" or not candidate_text:
                        self.logger.info(
                            "Auto mode: LLM determined no tools needed"
                        )
                        return []

                    selected_categories = []
                    for candidate in candidate_texts:
                        selected_categories = self._parse_selected_categories(
                            candidate,
                            available_categories,
                        )
                        if selected_categories:
                            break

                    if not selected_categories and len(candidate_texts) > 1:
                        selected_categories = self._parse_selected_categories(
                            " ".join(candidate_texts),
                            available_categories,
                        )

                    if not selected_categories:
                        self.logger.info(
                            "Auto mode: No valid categories parsed, defaulting "
                            "to search"
                        )
                        selected_categories = ["search"]

                    self.logger.info(
                        "Auto mode (LLM): Selected %s categories: %s",
                        len(selected_categories),
                        selected_categories,
                    )
                    return selected_categories
        except Exception as exc:
            self.logger.warning(
                "LLM classification failed: %s, falling back to all tools",
                exc,
            )

        self.logger.info(
            "Auto mode: Classification unavailable, providing broad tool "
            "access"
        )
        return ["search", "system", "math"]
