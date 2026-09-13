"""Current state of workflow execution."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from airunner_services.llm.agents.workflow_state.phase import Phase
from airunner_services.llm.agents.workflow_state.todo_item import TodoItem
from airunner_services.llm.agents.workflow_state.todo_status import TodoStatus
from airunner_services.llm.agents.workflow_state.workflow_definition import (
    WorkflowDefinition,
)
from airunner_services.llm.agents.workflow_state.workflow_type import (
    WorkflowType,
)


@dataclass
class WorkflowState:
    """Current state of workflow execution.

    This is the core state object that gets passed through the LangGraph
    workflow and enables structured multi-phase execution.
    """

    # Workflow identification
    workflow_type: WorkflowType = WorkflowType.SIMPLE
    workflow_definition: Optional[WorkflowDefinition] = None

    # Phase tracking
    current_phase: Phase = Phase.DISCOVERY
    phase_step: int = 0
    phase_history: List[Dict[str, Any]] = field(default_factory=list)

    # TODO list for structured execution
    todo_list: List[TodoItem] = field(default_factory=list)
    current_todo_id: Optional[str] = None

    # Artifacts collected during workflow
    artifacts: Dict[str, Any] = field(default_factory=dict)
    # Example artifacts:
    # - "notes": str - Discovery notes
    # - "design_doc": str - Planning document
    # - "todo_plan": List[str] - Planned tasks
    # - "code_files": Dict[str, str] - Written code
    # - "test_results": List[Dict] - Test execution results
    # - "research_sources": List[str] - URLs/documents found

    # Execution tracking
    tools_used: List[str] = field(default_factory=list)
    iterations: int = 0
    max_iterations: int = 50

    # Error handling
    last_error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3

    def to_dict(self) -> Dict[str, Any]:
        """Convert state to dictionary for LangGraph."""
        return {
            "workflow_type": self.workflow_type.value,
            "current_phase": self.current_phase.value,
            "phase_step": self.phase_step,
            "todo_list": [
                {
                    "id": t.id,
                    "title": t.title,
                    "description": t.description,
                    "status": t.status.value,
                    "phase": t.phase.value if t.phase else None,
                }
                for t in self.todo_list
            ],
            "current_todo_id": self.current_todo_id,
            "artifacts": self.artifacts,
            "iterations": self.iterations,
        }

    def get_current_todo(self) -> Optional[TodoItem]:
        """Get the currently active TODO item."""
        if not self.current_todo_id:
            return None
        for todo in self.todo_list:
            if todo.id == self.current_todo_id:
                return todo
        return None

    def get_next_todo(self) -> Optional[TodoItem]:
        """Get the next TODO item to work on."""
        for todo in self.todo_list:
            if todo.status == TodoStatus.NOT_STARTED:
                # Check dependencies
                deps_met = all(
                    any(
                        t.id == dep and t.status == TodoStatus.COMPLETED
                        for t in self.todo_list
                    )
                    for dep in todo.dependencies
                )
                if deps_met:
                    return todo
        return None

    def mark_todo_complete(
        self, todo_id: str, artifacts: Optional[Dict] = None
    ) -> bool:
        """Mark a TODO item as complete."""
        for todo in self.todo_list:
            if todo.id == todo_id:
                todo.status = TodoStatus.COMPLETED
                todo.completed_at = datetime.utcnow().isoformat()
                if artifacts:
                    todo.artifacts.update(artifacts)
                if self.current_todo_id == todo_id:
                    self.current_todo_id = None
                return True
        return False

    def add_todo(
        self,
        title: str,
        description: str,
        phase: Optional[Phase] = None,
        dependencies: Optional[List[str]] = None,
    ) -> TodoItem:
        """Add a new TODO item."""
        todo_id = f"todo_{len(self.todo_list) + 1}"
        todo = TodoItem(
            id=todo_id,
            title=title,
            description=description,
            phase=phase or self.current_phase,
            dependencies=dependencies or [],
        )
        self.todo_list.append(todo)
        return todo

    def transition_phase(self, new_phase: Phase) -> bool:
        """Transition to a new phase."""
        self.phase_history.append(
            {
                "from_phase": self.current_phase.value,
                "to_phase": new_phase.value,
                "step": self.phase_step,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )
        self.current_phase = new_phase
        self.phase_step = 0
        return True

    def can_transition(self) -> bool:
        """Check if we can transition to next phase."""
        if not self.workflow_definition:
            return True

        phase_def = self.workflow_definition.get_phase(self.current_phase)
        if not phase_def:
            return True

        # Check if required steps are done
        # This is simplified - real implementation would check artifacts
        return True

    def is_complete(self) -> bool:
        """Check if workflow is complete."""
        if self.current_phase == Phase.COMPLETE:
            return True

        # All TODOs complete
        if self.todo_list and all(
            t.status in (TodoStatus.COMPLETED, TodoStatus.SKIPPED)
            for t in self.todo_list
        ):
            return True

        return False
