"""A single TODO item in the workflow."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from airunner_services.llm.agents.workflow_state.phase import Phase
from airunner_services.llm.agents.workflow_state.todo_status import TodoStatus


@dataclass
class TodoItem:
    """A single TODO item in the workflow."""

    id: str
    title: str
    description: str
    status: TodoStatus = TodoStatus.NOT_STARTED
    phase: Optional[Phase] = None
    parent_id: Optional[str] = None  # For sub-tasks
    dependencies: List[str] = field(default_factory=list)
    artifacts: Dict[str, Any] = field(
        default_factory=dict
    )  # Output from this task
    created_at: str = field(
        default_factory=lambda: datetime.utcnow().isoformat()
    )
    completed_at: Optional[str] = None
