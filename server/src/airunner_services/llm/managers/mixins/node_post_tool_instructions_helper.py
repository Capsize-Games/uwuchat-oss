"""Post-tool instruction helpers for node functions."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import BaseMessage

from airunner_services.llm.managers.mixins.node_research_post_tool_helper import (
    NodeResearchPostToolHelper,
)

# Code-mode proxy tools that execute real work in the project worktree.
# Their result is a STEP in a multi-step task, not necessarily the end —
# unlike a completed todo item, a successful grep/read/edit is often
# followed by more tool calls.  In code mode we must NOT force-stop
# after one of these succeeds.
_CODE_MODE_TOOLS = {
    "apply_diff",
    "codebase_search",
    "edit_file",
    "execute_command",
    "list_files",
    "list_registered_projects",
    "read_file",
    "run_tests",
    "search_replace",
    "write_to_file",
}


def _code_mode_error_instruction(error: str) -> str:
    """Return the code-mode error-recovery instruction for *error*.

    Code mode: a tool that genuinely failed (path escape, missing
    file, permission denial) must be retried with the ACTUAL code
    tools, not the async-workflow tooling (transition_phase /
    add_todo_item / start_todo_item) that is not even bound in code
    mode.  Telling a code agent to call workflow tools that don't
    exist forces it into a dead end — it can neither recover nor
    finish, so it narrates instead of acting.
    """
    return (
        "\n\n=== CRITICAL: TOOL RETURNED AN ERROR — RECOVER AND "
        "RETRY ===\n"
        "The previous tool call FAILED. Read the error message "
        "carefully and fix the underlying cause:\n\n"
        "**ERROR MESSAGE:**\n"
        f"{error[:800]}\n\n"
        "**NEXT ACTION:** Call the appropriate tool NOW to recover:\n"
        "- Wrong/absolute path? Re-call the file tool with a path "
        "relative to the project worktree root.\n"
        "- Missing file? List the directory (list_files) to find "
        "the real name, then re-read/edit it.\n"
        "- Command failed? Fix the command (check the error "
        "output) and re-run it.\n"
        "- Wrong project? Call list_registered_projects to get the "
        "exact registered project name.\n\n"
        "Do NOT respond with text, do NOT claim the task is done "
        "— call a tool to actually fix it."
    )


class NodePostToolInstructionsHelper:
    """Build post-tool guidance for the workflow model."""

    # Tools whose successful result IS the answer — the model must relay
    # it, never relevance-gate it.  Includes the code-mode proxy tools
    # (execute_command, read_file, ...) whose output (gh issue list,
    # file contents) is inherently the response to the user's request;
    # gating those through the relevance checker produced false
    # "results not relevant" steering (e.g. "airunner (/path)" judged
    # unrelated to "list open issues").
    TASK_COMPLETING_TOOLS = {
        "complete_todo_item",
        "write_file",
        # Code-mode proxy tools (see projects/uwuchat/server/tools/
        # code_tools/) — their results are the answer, not search
        # fodder.  execute_command output, file reads/writes, project
        # listings, test runs all relay directly to the user.
        "apply_diff",
        "codebase_search",
        "edit_file",
        "execute_command",
        "list_files",
        "list_registered_projects",
        "read_file",
        "run_tests",
        "search_replace",
        "write_to_file",
    }

    def __init__(self, owner) -> None:
        """Store the owning workflow manager."""
        self._owner = owner
        self._research_helper = NodeResearchPostToolHelper()

    def add_post_tool_instructions(
        self,
        system_prompt: str,
        trimmed_messages: list[BaseMessage],
    ) -> str:
        """Return *system_prompt* with post-tool guidance appended.

        Only messages from the *current turn* (after the last
        ``HumanMessage``) are considered for tool detection — stale
        ``ToolMessage`` objects from earlier turns must not trigger
        post-tool instructions or relevance checks.

        Prefer :meth:`get_post_tool_instruction_text` in new code so
        the instruction text can be injected into the per-turn block
        instead of modifying the cached system prompt.
        """
        text = self.get_post_tool_instruction_text(trimmed_messages)
        if not text:
            return system_prompt
        return f"{system_prompt}{text}"

    def get_post_tool_instruction_text(
        self,
        trimmed_messages: list[BaseMessage],
    ) -> str:
        """Return the post-tool instruction text, or empty string.

        Computes the same guidance as :meth:`add_post_tool_instructions`
        but returns only the appended portion — callers inject it into
        the per-turn / human-message block so it stays outside the
        cached system-prompt prefix.
        """
        turn_messages = self._messages_this_turn(trimmed_messages)
        tool_messages = self._tool_messages(turn_messages)
        if not tool_messages:
            return ""
        error_instruction = self._error_instruction(tool_messages)
        if error_instruction:
            self._owner.logger.info(
                "[POST-TOOL] Tool returned ERROR - injecting error "
                "handling instructions into per-turn block"
            )
            return error_instruction
        instruction = self._build_instruction(
            trimmed_messages, turn_messages, tool_messages,
        )
        self._owner.logger.info(
            "[POST-TOOL] Instruction text length: %d chars",
            len(instruction),
        )
        self._log_tool_results(tool_messages)
        return instruction

    @staticmethod
    def _messages_this_turn(
        trimmed_messages: list[BaseMessage],
    ) -> list[BaseMessage]:
        """Return the slice of *trimmed_messages* after the last human turn.

        Conversation turns follow ``HumanMessage → [AIMessage(tool_calls)
        → ToolMessage]* → AIMessage(final)``, so everything after the
        most recent ``HumanMessage`` belongs to the current turn.
        """
        for i in range(len(trimmed_messages) - 1, -1, -1):
            if trimmed_messages[i].__class__.__name__ == "HumanMessage":
                return trimmed_messages[i + 1:]
        return trimmed_messages

    @staticmethod
    def _tool_messages(
        trimmed_messages: list[BaseMessage],
    ) -> list[BaseMessage]:
        """Return the tool messages from one trimmed message list."""
        return [
            message
            for message in trimmed_messages
            if message.__class__.__name__ == "ToolMessage"
        ]

    def _error_instruction(self, tool_messages: list[BaseMessage]) -> str:
        """Return one error-recovery instruction when the LAST tool failed.

        Only the most recent tool result matters.  A stale error from an
        earlier step in the same turn must not poison later iterations:
        the model may recover from a bad path, then successfully edit,
        and the success must get the CONTINUE WORKING / USE TOOL RESULTS
        instruction — not a re-injection of the old error.  This mirrors
        ``_tool_succeeded``, which also only inspects the last message.
        """
        if not tool_messages:
            return ""
        content = str(getattr(tool_messages[-1], "content", ""))
        if not (content.startswith("ERROR:") or content.startswith("Error:")):
            return ""
        if self._code_mode_active():
            self._owner.logger.info(
                "[POST-TOOL] Code mode tool error — code-mode recovery "
                "instruction injected",
            )
            return _code_mode_error_instruction(content)
        return (
            "\n\n=== CRITICAL: TOOL RETURNED AN ERROR - YOU MUST CALL A TOOL ===\n"
            "The previous tool call FAILED. Read the error message carefully.\n\n"
            "**ERROR MESSAGE:**\n"
            f"{content[:800]}\n\n"
            "**YOU MUST DO ONE OF THESE:**\n"
            "1. Call the tool suggested in the error message (e.g., transition_phase, add_todo_item, start_todo_item)\n"
            "2. Follow the workflow steps exactly as described in the error\n\n"
            "**DO NOT:**\n"
            "- Claim the file was created (IT WAS NOT)\n"
            "- Skip workflow steps\n"
            "- Respond with text saying you completed the task\n"
            "- Give the user any output without first fixing the workflow state\n\n"
            "**NEXT ACTION:** Call one of these workflow tools:\n"
            "- transition_phase('planning', 'reason') - to move to next phase\n"
            "- add_todo_item('title', 'description') - to create a task\n"
            "- start_todo_item('todo_1') - to begin working on a task\n\n"
            "Call a tool NOW. Do not respond with text."
        )

    def _build_instruction(
        self,
        trimmed_messages: list[BaseMessage],
        turn_messages: list[BaseMessage],
        tool_messages: list[BaseMessage],
    ) -> str:
        """Return the post-tool instruction for the current workflow mode."""
        response_format = getattr(self._owner, "_response_format", None)
        force_tool = getattr(self._owner, "_force_tool", None)
        tool_calling_mode = getattr(
            self._owner._chat_model, "tool_calling_mode", "react"
        )
        # Count only this turn's tool calls, not stale calls from
        # earlier turns that now persist in history.
        tool_call_count = len(
            [
                message
                for message in turn_messages
                if hasattr(message, "tool_calls") and message.tool_calls
            ]
        )
        scrape_attempts = sum(
            1
            for message in turn_messages
            if hasattr(message, "tool_calls") and message.tool_calls
            for tool_call in message.tool_calls
            if tool_call.get("name") == "scrape_website"
        )
        successful_scrapes, failed_scrapes = (
            self._research_helper.scrape_counts(tool_messages)
        )
        search_urls = self._research_helper.search_urls(tool_messages)
        self._owner.logger.info(
            "[POST-TOOL] response_format=%s, tool_calling_mode=%s, force_tool=%s, "
            "is_research_mode=%s, tool_calls=%s, scrape_attempts=%s, "
            "successful_scrapes=%s, failed_scrapes=%s, search_urls=%s",
            response_format,
            tool_calling_mode,
            force_tool,
            force_tool == "search_web",
            tool_call_count,
            scrape_attempts,
            successful_scrapes,
            failed_scrapes,
            len(search_urls),
        )
        if force_tool == "search_web":
            return self._research_helper.research_instruction(
                tool_call_count,
                scrape_attempts,
                successful_scrapes,
                failed_scrapes,
                search_urls,
            )
        if response_format == "json":
            return (
                "\n\n=== CRITICAL RESPONSE FORMAT REQUIREMENT ===\n"
                "You have tool results in the conversation above. "
                "Now answer the user's question using that information.\n"
                "YOU MUST respond ONLY with valid JSON in the EXACT format specified in the system prompt above.\n"
                "Do NOT write conversational text. Do NOT explain or narrate. ONLY output the JSON object.\n"
                "Your entire response must be parseable JSON - nothing else."
            )
        if response_format is not None and response_format != "conversational":
            return (
                "\n\n=== CRITICAL: USE TOOL RESULTS ===\n"
                "You have tool results in the conversation above. "
                "Answer the user's question using that information. "
                f"Respond in {response_format} format."
            )
        return self._default_instruction(
            trimmed_messages, turn_messages, tool_messages,
        )

    def _code_mode_active(self) -> bool:
        """Return True when the current conversation has code mode on.

        Delegates to the shared framework helper so the post-tool
        instruction layer agrees with the tool filter, prompt builder,
        agentic guard, and streaming config about whether the current
        conversation is in code mode.
        """
        from airunner_services.llm.managers.mixins.code_mode_detection import (
            code_mode_active_for_owner,
        )

        return code_mode_active_for_owner(self._owner)

    def _default_instruction(
        self,
        trimmed_messages: list[BaseMessage],
        turn_messages: list[BaseMessage],
        tool_messages: list[BaseMessage],
    ) -> str:
        """Return the default post-tool instruction for conversational mode."""
        last_tool_name = self._last_tool_name(turn_messages)
        tool_succeeded = self._tool_succeeded(tool_messages)
        code_mode = self._code_mode_active()
        if (
            code_mode
            and last_tool_name in _CODE_MODE_TOOLS
            and tool_succeeded
        ):
            # Code mode: a successful code tool is a STEP, not the end.
            # Let the agent continue calling tools until the task is
            # actually done.  Only stop when the user's request is a
            # single tool round (the model signals done itself).
            self._owner.logger.info(
                "[POST-TOOL] Code mode active — tool '%s' succeeded; "
                "allowing continued tool calls",
                last_tool_name,
            )
            # Steer the model toward EDITING when it has been exploring
            # (grep/read/list) without yet making any change.  Qwen 9B
            # tends to re-verify with greps and reads forever; an
            # explicit push toward the edit tools breaks that loop.
            explore_names = {"execute_command", "read_file", "list_files",
                             "codebase_search", "list_registered_projects"}
            edit_names = {"search_replace", "write_to_file", "apply_diff",
                          "edit_file"}
            turn_calls = [
                tc.get("name")
                for m in turn_messages
                if hasattr(m, "tool_calls") and m.tool_calls
                for tc in m.tool_calls
            ]
            explores = sum(1 for n in turn_calls if n in explore_names)
            edits = sum(1 for n in turn_calls if n in edit_names)
            if explores >= 3 and edits == 0:
                self._owner.logger.info(
                    "[POST-TOOL] Code mode: %d explore calls, 0 edits — "
                    "pushing toward edit tools", explores,
                )
                return (
                    "\n\n=== CONTINUE WORKING — NOW EDIT ===\n"
                    "You have explored enough (grep/read/list). The next"
                    " tool MUST be a CHANGE to a file you have already"
                    " inspected: search_replace, write_to_file, apply_diff,"
                    " or edit_file. Do NOT run another grep, read, or list."
                    " Take the file path and exact strings from the tool"
                    " results above and call the edit tool on that file"
                    " NOW."
                )
            return (
                "\n\n=== CONTINUE WORKING ===\n"
                "The tool above succeeded and its result is now part of"
                " the conversation. Continue the task:\n"
                "- If more steps remain (edit files, run commands,"
                " verify), call the next tool NOW — do not stop early.\n"
                "- Only respond with a final text answer when the"
                " entire task is genuinely complete (all files edited"
                " and verified).\n"
                "- Be concise in any text; let the tools do the work."
            )
        if last_tool_name in self.TASK_COMPLETING_TOOLS and tool_succeeded:
            self._owner.logger.info(
                "[POST-TOOL] Task-completing tool '%s' succeeded - instructing model to respond (not call more tools)",
                last_tool_name,
            )
            return (
                "\n\n=== TASK COMPLETED - RESPOND TO USER ===\n"
                "The requested task has been completed successfully!\n\n"
                "**YOUR NEXT ACTION:** Respond to the user with a summary.\n"
                "- Tell them what was accomplished\n"
                "- Include the file path or result from the tool output\n"
                "- Keep it brief and friendly\n\n"
                "**DO NOT:**\n"
                "- Call more tools (the task is DONE)\n"
                "- Start a new task without being asked\n"
                "- Give a generic greeting\n\n"
                "Example response: 'Done! I created hello_world.py with your function.'"
            )
        # Check whether the tool results are relevant to the user's
        # actual question before insisting on synthesis.
        tool_content = str(
            getattr(tool_messages[-1], "content", "")
        )
        user_question = self._get_user_question(trimmed_messages)
        relevant = self._results_are_relevant(tool_content, user_question)
        if not relevant:
            self._owner.logger.info(
                "[POST-TOOL] Results not relevant — steering "
                "toward honest fallback"
            )
            return (
                "\n\nThe tool results above do not address what the"
                " user asked. Do NOT force a connection or synthesize"
                " something that is not there. Tell the user plainly"
                " that you searched and did not find anything relevant"
                " to their specific question — do not recite anything"
                " else instead."
            )
        return (
            "\n\n=== CRITICAL: USE TOOL RESULTS ===\n"
            "Tool results are available in the conversation above.\n"
            "IMPORTANT: You MUST use these tool results to answer the user's question.\n"
            "Do NOT ignore the tool results. Do NOT give a generic greeting.\n"
            "Synthesize the information from the tool results into a helpful, conversational response.\n"
            "If the tool returned search results, summarize the key information for the user."
        )

    def _results_are_relevant(
        self, tool_content: str, user_question: str
    ) -> bool:
        """Return True when tool results are relevant to the question."""
        from airunner_services.llm.managers.concerns.relevance_check import (
            check_relevance,
        )
        fast_model = self._resolve_fast_model()
        return check_relevance(
            tool_content, user_question, fast_model, self._owner.logger
        )

    def _resolve_fast_model(self) -> Any | None:
        """Return a cheap classification model, or None."""
        specialized = getattr(
            self._owner, "_specialized_chat_models", {}
        )
        return (
            specialized.get("TOOL_CLASSIFICATION")
            or getattr(self._owner, "_original_chat_model", None)
            or getattr(self._owner, "_chat_model", None)
        )

    @staticmethod
    def _get_user_question(messages: list[BaseMessage]) -> str:
        """Return the most recent human message content."""
        for msg in reversed(messages):
            if msg.__class__.__name__ == "HumanMessage":
                content = getattr(msg, "content", "")
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    for block in content:
                        if (
                            isinstance(block, dict)
                            and block.get("type") == "text"
                        ):
                            return str(block.get("text", ""))
        return ""

    @staticmethod
    def _last_tool_name(trimmed_messages: list[BaseMessage]) -> str | None:
        """Return the last requested tool name from AI messages."""
        ai_messages = [
            message
            for message in trimmed_messages
            if hasattr(message, "tool_calls") and message.tool_calls
        ]
        if not ai_messages or not ai_messages[-1].tool_calls:
            return None
        return ai_messages[-1].tool_calls[-1].get("name")

    @staticmethod
    def _tool_succeeded(tool_messages: list[BaseMessage]) -> bool:
        """Return whether the last tool message indicates success.

        A tool result is treated as successful when it contains a
        success indicator OR when it is a non-error result from one of
        the code-mode proxy tools — those tools (execute_command, gh
        output, file reads, project listings) return data as their
        content with no "successfully"/"done" marker, yet a non-ERROR
        result is a successful execution.
        """
        if not tool_messages:
            return False
        last_tool_content = str(getattr(tool_messages[-1], "content", ""))
        if last_tool_content.startswith("ERROR:") or (
            last_tool_content.startswith("Error:")
        ):
            return False
        indicators = [
            "created",
            "successfully",
            "written",
            "✓",
            "complete",
            "done",
        ]
        if any(
            indicator in last_tool_content.lower() for indicator in indicators
        ):
            return True
        # Code-mode proxy tool results (gh output, file contents,
        # project listings) carry no success marker — a non-error
        # content from these tools is a successful execution.
        return True

    def _log_tool_results(self, tool_messages: list[BaseMessage]) -> None:
        """Log previews of available tool results."""
        self._owner.logger.info(
            "Model has access to %s tool result(s)",
            len(tool_messages),
        )
        for index, tool_message in enumerate(tool_messages, start=1):
            result_len = len(str(tool_message.content)) if hasattr(
                tool_message, "content"
            ) else 0
            self._owner.logger.info(
                "  Tool result %s: %d chars",
                index,
                result_len,
            )
