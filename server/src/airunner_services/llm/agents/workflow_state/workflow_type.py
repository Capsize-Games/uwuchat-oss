"""Types of workflows the agent can execute."""

from enum import Enum


class WorkflowType(Enum):
    """Types of workflows the agent can execute."""

    CODING = "coding"  # Legacy compatibility value
    RESEARCH = "research"
    WRITING = "writing"
    MATH = "math"
    DYNAMIC = "dynamic"  # LLM-defined workflow
    SIMPLE = "simple"  # Single-turn, no workflow needed
