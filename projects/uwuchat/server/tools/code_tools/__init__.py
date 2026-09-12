"""Code tools — headlesscode session launch + inline agent tool proxy.

Importing this package triggers tool registration via the @tool
decorators.
"""

from projects.uwuchat.server.tools.code_tools.launch_session import (
    launch_headlesscode_session,
)
from projects.uwuchat.server.tools.code_tools.proxy_file_tools import (
    apply_diff,
    edit_file,
    search_replace,
    write_to_file,
)
from projects.uwuchat.server.tools.code_tools.proxy_tools import (
    codebase_search,
    execute_command,
    list_files,
    read_file,
    run_tests,
)
from projects.uwuchat.server.tools.code_tools.registry_tool import (
    list_registered_projects,
)

__all__ = [
    "apply_diff",
    "codebase_search",
    "edit_file",
    "execute_command",
    "launch_headlesscode_session",
    "list_files",
    "list_registered_projects",
    "read_file",
    "run_tests",
    "search_replace",
    "write_to_file",
]
