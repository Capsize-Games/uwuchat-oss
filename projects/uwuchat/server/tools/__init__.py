"""LLM tools for UwUChat productivity features.

Importing this package triggers tool registration via the @tool decorators.
"""

from projects.uwuchat.server.tools.calendar_tools import (
    add_calendar_event,
    add_recurring_reminder,
    delete_calendar_event,
    list_calendar_events,
    update_calendar_event,
)
from projects.uwuchat.server.tools.code_tools import (
    apply_diff,
    codebase_search,
    edit_file,
    execute_command,
    launch_headlesscode_session,
    list_files,
    list_registered_projects,
    read_file,
    run_tests,
    search_replace,
    write_to_file,
)
from projects.uwuchat.server.tools.email_tools import (
    search_email_knowledge,
)
from projects.uwuchat.server.tools.journal_tools import write_journal_entry
from projects.uwuchat.server.tools.mattermost_tools import (
    send_mattermost_message,
)
from projects.uwuchat.server.tools.task_tools import (
    add_goal,
    remember_task,
    update_task_status,
)
from projects.uwuchat.server.tools.weather_tools import (
    get_my_weather,
    search_weather,
)

__all__ = [
    "add_calendar_event",
    "add_goal",
    "add_recurring_reminder",
    "apply_diff",
    "codebase_search",
    "delete_calendar_event",
    "edit_file",
    "execute_command",
    "get_my_weather",
    "launch_headlesscode_session",
    "list_calendar_events",
    "list_files",
    "list_registered_projects",
    "read_file",
    "remember_task",
    "run_tests",
    "search_email_knowledge",
    "search_replace",
    "search_weather",
    "send_mattermost_message",
    "update_calendar_event",
    "update_task_status",
    "write_journal_entry",
    "write_to_file",
]
