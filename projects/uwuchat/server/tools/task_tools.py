"""LLM tools: remember_task, update_task_status, add_goal."""

from __future__ import annotations

import datetime
import logging
from typing import Annotated, Any

from airunner_services.llm.core.tool_registry import ToolCategory, tool


@tool(
    name="remember_task",
    category=ToolCategory.SYSTEM,
    description=(
        "Create a to-do item the UwU will track and follow up on. "
        "Call this when the user mentions something they need or want "
        "to do — 'I need to finish that report', 'remind me to buy "
        "groceries', 'I want to learn guitar'. The UwU will naturally "
        "ask about it later. Always confirm out loud."
    ),
    return_direct=False,
    requires_agent=True,
    defer_loading=True,
    keywords=[
        "task", "todo", "to-do", "remind", "follow up", "track",
        "remember to", "don't let me forget",
    ],
    input_examples=[
        {"title": "Finish quarterly report", "due_date": "2026-07-07"},
        {
            "title": "Buy groceries",
            "description": "Milk, eggs, bread, avocados",
            "goal_title": "Eat healthier",
        },
    ],
)
def remember_task(
    title: Annotated[
        str,
        "Short description of the task (e.g. 'Finish quarterly report').",
    ],
    due_date: Annotated[
        str | None,
        "ISO-format date when this should be done "
        "(e.g. '2026-07-07').",
    ] = None,
    description: Annotated[
        str | None,
        "Optional longer description or details.",
    ] = None,
    goal_title: Annotated[
        str | None,
        "If this task belongs to an existing goal, provide the goal's "
        "exact title. If the goal doesn't exist yet, it will be "
        "created.",
    ] = None,
    agent: Any = None,
) -> str:
    """Create a tracked task for the user."""
    user = getattr(agent, "user", None) if agent else None
    chatbot = getattr(agent, "chatbot", None) if agent else None
    user_id = getattr(user, "id", None) if user else None
    chatbot_id = getattr(chatbot, "id", None) if chatbot else None
    if not user_id or not chatbot_id:
        return (
            "I couldn't save that task — something's off with "
            "my session. Can we try again?"
        )

    goal_id = None
    if goal_title:
        goal_id = _resolve_or_create_goal(user_id, goal_title.strip())

    parsed_due = None
    if due_date:
        try:
            parsed_due = datetime.date.fromisoformat(due_date)
        except (ValueError, TypeError):
            logging.warning("Invalid due_date: %s", due_date)

    from projects.uwuchat.server.models.task import Task

    Task.objects.create(
        user_id=user_id,
        chatbot_id=chatbot_id,
        title=title.strip(),
        description=description.strip() if description else None,
        due_date=parsed_due,
        goal_id=goal_id,
    )

    lines = [f"Task '{title.strip()}' added to your list."]
    if parsed_due:
        lines.append(f"It's due {parsed_due.strftime('%B %-d')}.")
    if goal_title:
        lines.append(
            f"It's filed under your '{goal_title}' goal."
        )
    lines.append(
        "Let the user know in your voice that you'll keep track of it."
    )
    return " ".join(lines)


@tool(
    name="update_task_status",
    category=ToolCategory.SYSTEM,
    description=(
        "Update the status of a tracked task. Use when the user "
        "reports progress ('I finished the report!', 'I started "
        "working on that', 'I gave up on learning guitar'). "
        "Acknowledge the update warmly."
    ),
    return_direct=False,
    requires_agent=True,
    defer_loading=True,
    keywords=[
        "task status", "done", "finished", "completed", "progress",
        "gave up", "abandoned", "started",
    ],
    input_examples=[
        {"task_id": 42, "status": "done"},
        {"task_id": 42, "status": "in_progress"},
    ],
)
def update_task_status(
    task_id: Annotated[
        int,
        "The numeric ID of the task to update.",
    ],
    status: Annotated[
        str,
        "New status: 'open', 'in_progress', 'done', or 'abandoned'.",
    ],
    agent: Any = None,
) -> str:
    """Mark a task as done, in-progress, abandoned, or re-opened."""
    valid = {"open", "in_progress", "done", "abandoned"}
    if status not in valid:
        return (
            f"I don't know that status '{status}'. "
            f"Use one of: {', '.join(sorted(valid))}."
        )

    from projects.uwuchat.server.models.task import Task, TaskStatus

    task = Task.objects.get(task_id)
    if task is None:
        return (
            f"I couldn't find task #{task_id}. It may have been "
            "deleted or moved."
        )

    update_kwargs: dict = {"status": status}
    verb = "updated"

    if status == TaskStatus.DONE.value:
        update_kwargs["completed_at"] = datetime.datetime.now(
            datetime.timezone.utc
        )
        verb = "marked as done"
    elif status == TaskStatus.IN_PROGRESS.value:
        verb = "marked as in progress"
    elif status == TaskStatus.ABANDONED.value:
        verb = "marked as abandoned"
    elif status == TaskStatus.OPEN.value:
        update_kwargs["completed_at"] = None
        verb = "re-opened"

    Task.objects.update(task_id, **update_kwargs)
    return (
        f"Task '{task.title}' {verb}. Let the user know in your "
        "voice — acknowledge their progress warmly!"
    )


@tool(
    name="add_goal",
    category=ToolCategory.SYSTEM,
    description=(
        "Create a long-term personal goal. Use when the user expresses "
        "an ambition or target — 'I want to run a 5K by October', "
        "'My goal is to read 20 books this year', 'I'm going to learn "
        "Spanish'. Confirm enthusiastically."
    ),
    return_direct=False,
    requires_agent=True,
    defer_loading=True,
    keywords=[
        "goal", "ambition", "target", "resolution", "want to",
        "aiming to", "by next", "this year",
    ],
    input_examples=[
        {
            "title": "Run a 5K",
            "target_date": "2026-10-01",
            "description": (
                "Couch to 5K program, aiming for local Turkey Trot"
            ),
        },
    ],
)
def add_goal(
    title: Annotated[
        str,
        "Short title for the goal (e.g. 'Run a 5K').",
    ],
    description: Annotated[
        str | None,
        "Optional longer description.",
    ] = None,
    target_date: Annotated[
        str | None,
        "ISO-format date for the target deadline "
        "(e.g. '2026-10-01').",
    ] = None,
    agent: Any = None,
) -> str:
    """Create a long-term goal for the user."""
    user = getattr(agent, "user", None) if agent else None
    user_id = getattr(user, "id", None) if user else None
    if not user_id:
        return "I couldn't save that goal — session state is missing."

    parsed_target = None
    if target_date:
        try:
            parsed_target = datetime.date.fromisoformat(target_date)
        except (ValueError, TypeError):
            logging.warning("Invalid target_date: %s", target_date)

    from projects.uwuchat.server.models.goal import Goal

    Goal.objects.create(
        user_id=user_id,
        title=title.strip(),
        description=description.strip() if description else None,
        target_date=parsed_target,
    )

    lines = [f"Goal '{title.strip()}' created."]
    if parsed_target:
        lines.append(
            "I'll keep you on track for "
            + parsed_target.strftime("%B %-d, %Y")
            + "!"
        )
    lines.append(
        "Let the user know in your voice that you believe in them."
    )
    return " ".join(lines)


def _resolve_or_create_goal(user_id: int, title: str) -> int | None:
    """Look up a goal by title, creating it if not found."""
    from projects.uwuchat.server.models.goal import Goal

    row = (
        Goal.objects.query()
        .filter(
            Goal.user_id == user_id,
            Goal.title == title,
            Goal.deleted.is_(False),
        )
        .first()
    )
    if row:
        return row.id

    new_goal = Goal.objects.create(user_id=user_id, title=title)
    return new_goal.id if new_goal else None
