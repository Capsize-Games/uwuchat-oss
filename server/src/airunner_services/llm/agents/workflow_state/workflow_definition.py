"""Definition of a complete workflow."""

from dataclasses import dataclass
from typing import List, Optional

from airunner_services.llm.agents.workflow_state.phase import Phase
from airunner_services.llm.agents.workflow_state.phase_definition import (
    PhaseDefinition,
)
from airunner_services.llm.agents.workflow_state.workflow_type import (
    WorkflowType,
)


@dataclass
class WorkflowDefinition:
    """Definition of a complete workflow.

    Can be predefined (CODING, RESEARCH) or dynamically created by the LLM.
    """

    workflow_type: WorkflowType
    name: str
    description: str
    phases: List[PhaseDefinition]
    initial_phase: Phase = Phase.DISCOVERY

    def get_phase(self, phase: Phase) -> Optional[PhaseDefinition]:
        """Get phase definition by phase enum."""
        for p in self.phases:
            if p.name == phase:
                return p
        return None

    def get_next_phase(self, current: Phase) -> Optional[Phase]:
        """Get the next phase after current."""
        phase_order = [p.name for p in self.phases]
        try:
            idx = phase_order.index(current)
            if idx + 1 < len(phase_order):
                return phase_order[idx + 1]
        except ValueError:
            pass
        return None
