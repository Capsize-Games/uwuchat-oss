"""Prompt builders for workflow continuation and forced responses."""
# IMPORTANT: All prompt strings in this file must stay generic.
# Never embed real-world names, events, current affairs, or any
# topic drawn from a test conversation. Prompt text runs in every
# user session — specific content becomes hallucination fuel.

from __future__ import annotations

DEFAULT_WORKFLOW_NEXT_ACTION = (
    "Call transition_phase('planning', " "'Simple task, moving to planning')"
)


def extract_next_workflow_action(tool_content: str) -> str:
    """Return the next workflow action encoded in tool output."""
    if not tool_content:
        return ""

    next_call_marker = "YOUR NEXT TOOL CALL:"
    immediate_action_marker = "IMMEDIATE NEXT ACTION"
    immediate_call_marker = "Call this tool NOW:"

    if next_call_marker in tool_content:
        for line in tool_content.splitlines():
            if next_call_marker in line:
                return line.split(next_call_marker, maxsplit=1)[-1].strip()

    if immediate_action_marker in tool_content:
        lines = tool_content.splitlines()
        for index, line in enumerate(lines):
            if immediate_call_marker in line and index + 1 < len(lines):
                return lines[index + 1].strip()

    return ""


def build_workflow_correction_prompt(
    tool_name: str,
    user_question: str,
    next_action: str,
) -> str:
    """Return the duplicate-workflow correction prompt."""
    action_line = (
        f"REQUIRED: Call {next_action}"
        if next_action
        else DEFAULT_WORKFLOW_NEXT_ACTION
    )
    lines = [
        (
            f"[SYSTEM CORRECTION] You called {tool_name} twice. "
            "The workflow is ALREADY ACTIVE."
        ),
        "",
        "DO NOT output any text response. DO NOT explain what you will do.",
        "You MUST call a workflow tool NOW.",
        "",
        action_line,
        "",
        f"Your task: {user_question}",
        "",
        "CALL THE TOOL NOW. NO TEXT RESPONSE.",
    ]
    return "\n".join(lines)


def build_workflow_continuation_prompt(
    tool_name: str,
    user_question: str,
    tool_content: str,
    next_action: str,
) -> str:
    """Return the prompt that nudges the model to continue a workflow."""
    next_step_line = (
        f"The next step is: {next_action}"
        if next_action
        else "Follow the instructions in the workflow status above."
    )
    lines = [
        (
            "You already started the workflow. The workflow has given you "
            "specific instructions."
        ),
        "",
        "WORKFLOW STATUS:",
        tool_content[:1500],
        "",
        (
            f"CRITICAL: You called {tool_name} twice. The workflow is "
            "already active!"
        ),
        "",
        next_step_line,
        "",
        (
            f"DO NOT call {tool_name} again. Instead, call the NEXT tool "
            "in the sequence."
        ),
        "",
        "For a structured workflow, the typical sequence is:",
        "1. start_workflow (DONE - you already did this)",
        "2. transition_phase('planning', 'reason')",
        "3. add_todo_item('title', 'description')",
        "4. transition_phase('execution', 'reason')",
        "5. start_todo_item('todo_id')",
        "6. use the task tools needed for that TODO",
        "7. complete_todo_item('todo_id')",
        "8. transition_phase('complete', 'All done')",
        "",
        f"User's original request: {user_question}",
        "",
        (
            "Now call the NEXT workflow tool to continue. Do NOT repeat "
            "start_workflow."
        ),
    ]
    return "\n".join(lines)


def build_tool_result_response_prompt(
    tool_results: list[tuple[str, str]] | str | None = None,
    user_question: str = "",
    *,
    all_tool_content: str | None = None,
) -> str:
    """Return the synthesis prompt for multi-tool results.

    Accepts both the new ``list[tuple[str, str]]`` format and the
    legacy single-string format (via ``all_tool_content=`` kwarg or
    passing a bare string as the first argument).

    Args:
        tool_results: List of ``(tool_name, content)`` pairs, or a
            legacy plain-string tool content.
        user_question: The original user message being answered.
        all_tool_content: Deprecated single-string form.  When
            provided (and ``tool_results`` is not a list), it is
            wrapped as ``[("unknown", all_tool_content)]``.
    """
    # ---- resolve call format ------------------------------------------
    if isinstance(tool_results, str):
        pairs: list[tuple[str, str]] = [
            ("unknown", tool_results),
        ]
    elif isinstance(tool_results, list):
        pairs = tool_results
    elif all_tool_content:
        pairs = [("unknown", all_tool_content)]
    else:
        pairs = []

    # ---- render labeled blocks ----------------------------------------
    lines: list[str] = []
    if user_question:
        lines.extend([f"Respond to: {user_question}", ""])

    block_labels: dict[str, str] = {
        "get_topic_brief": "Search results",
        "search_fastsearch": "Search results",
        "search_fastsearch_news": "Search results",
        "search_news": "Search results",
        "recall_knowledge": "Recalled memories",
        "save_knowledge": "Saved fact",
    }

    for tool_name, content in pairs:
        label = block_labels.get(tool_name, f"Tool: {tool_name}")
        lines.extend([f"[{label}]", content, ""])

    lines.extend(
        [
            (
                "Use the sources above to inform your response."
                " Where they directly address what was asked, cite them"
                " confidently."
            ),
            (
                "Do NOT claim to remember things not present in"
                " [Recalled memories]. If [Recalled memories] is absent"
                " or empty, express genuine uncertainty rather than"
                " confabulating — never say 'I remember' without"
                " evidence."
            ),
            (
                "Do not reference these lookups or mention searching."
                " Stay fully in character throughout. Do not call tools"
                " or output JSON."
            ),
        ]
    )
    return "\n".join(lines)
