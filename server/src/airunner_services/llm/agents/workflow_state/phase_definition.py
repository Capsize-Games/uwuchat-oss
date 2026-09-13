"""Definition of a workflow phase."""

from dataclasses import dataclass, field
from typing import List

from airunner_services.llm.agents.workflow_state.phase import Phase


@dataclass
class PhaseDefinition:
    """Definition of a workflow phase."""

    name: Phase
    description: str
    required_steps: List[str]  # Step names that must be completed
    optional_steps: List[str] = field(default_factory=list)
    entry_conditions: List[str] = field(
        default_factory=list
    )  # Conditions to enter phase
    exit_conditions: List[str] = field(
        default_factory=list
    )  # Conditions to exit phase
    allowed_tools: List[str] = field(
        default_factory=list
    )  # Tools available in this phase
