"""Predefined workflow definitions and the workflow registry."""

from typing import Any, Dict, List, Optional

from airunner_services.llm.agents.workflow_state.phase import Phase
from airunner_services.llm.agents.workflow_state.phase_definition import (
    PhaseDefinition,
)
from airunner_services.llm.agents.workflow_state.workflow_definition import (
    WorkflowDefinition,
)
from airunner_services.llm.agents.workflow_state.workflow_type import (
    WorkflowType,
)


CODING_WORKFLOW = WorkflowDefinition(
    workflow_type=WorkflowType.CODING,
    name="Coding Workflow",
    description="Legacy structured implementation workflow",
    phases=[
        PhaseDefinition(
            name=Phase.DISCOVERY,
            description="Understand the task and gather context",
            required_steps=["understand_task", "gather_context", "take_notes"],
            allowed_tools=[
                "semantic_search",
                "read_file",
                "grep_search",
                "record_knowledge",
            ],
        ),
        PhaseDefinition(
            name=Phase.PLANNING,
            description="Review notes, create a plan, and define TODOs",
            required_steps=["review_notes", "create_plan", "create_todos"],
            allowed_tools=["recall_knowledge", "manage_todos"],
        ),
        PhaseDefinition(
            name=Phase.EXECUTION,
            description="Execute TODO items and verify the result",
            required_steps=["implement_task", "verify_result"],
            allowed_tools=[
                "write_file",
                "edit_file",
                "run_tests",
                "run_command",
                "read_file",
                "manage_todos",
            ],
            exit_conditions=["all_todos_complete", "all_tests_pass"],
        ),
        PhaseDefinition(
            name=Phase.REVIEW,
            description="Review changes and confirm the deliverable",
            required_steps=["review_changes", "confirm_outcome"],
            allowed_tools=["read_file", "edit_file", "run_tests"],
        ),
        PhaseDefinition(
            name=Phase.COMPLETE,
            description="Workflow complete",
            required_steps=[],
        ),
    ],
)


RESEARCH_WORKFLOW = WorkflowDefinition(
    workflow_type=WorkflowType.RESEARCH,
    name="Deep Research Workflow",
    description="Structured workflow for comprehensive research",
    phases=[
        PhaseDefinition(
            name=Phase.DISCOVERY,
            description="Understand topic and gather initial sources",
            required_steps=[
                "understand_topic",
                "initial_search",
                "collect_sources",
            ],
            allowed_tools=[
                "search_web",
                "search_news",
                "scrape_website",
                "record_knowledge",
            ],
        ),
        PhaseDefinition(
            name=Phase.PLANNING,
            description="Review findings and create an evidence-backed outline",
            required_steps=[
                "review_sources",
                "identify_gaps",
                "create_outline",
            ],
            allowed_tools=[
                "recall_knowledge",
                "search_web",
                "search_news",
                "scrape_website",
            ],
        ),
        PhaseDefinition(
            name=Phase.EXECUTION,
            description="Synthesize findings with citations and fact-checking",
            required_steps=["write_sections", "cite_sources", "fact_check"],
            allowed_tools=[
                "recall_knowledge",
                "search_web",
                "search_news",
                "scrape_website",
            ],
        ),
        PhaseDefinition(
            name=Phase.REVIEW,
            description="Review synthesis, fill gaps, and finalize response",
            required_steps=["review_document", "fill_gaps", "finalize"],
            allowed_tools=["search_web", "search_news", "scrape_website"],
        ),
        PhaseDefinition(
            name=Phase.COMPLETE,
            description="Research complete",
            required_steps=[],
        ),
    ],
)


WRITING_WORKFLOW = WorkflowDefinition(
    workflow_type=WorkflowType.WRITING,
    name="Writing Workflow",
    description="Structured workflow for creative/technical writing",
    phases=[
        PhaseDefinition(
            name=Phase.DISCOVERY,
            description="Understand requirements and gather inspiration",
            required_steps=["understand_requirements", "gather_references"],
            allowed_tools=["search_web", "rag_search", "record_knowledge"],
        ),
        PhaseDefinition(
            name=Phase.PLANNING,
            description="Create outline and structure",
            required_steps=["create_outline", "plan_sections"],
            allowed_tools=["create_document", "recall_knowledge"],
        ),
        PhaseDefinition(
            name=Phase.EXECUTION,
            description="Write content",
            required_steps=["write_draft", "revise"],
            allowed_tools=["create_document", "edit_document"],
        ),
        PhaseDefinition(
            name=Phase.REVIEW,
            description="Review and polish",
            required_steps=["proofread", "finalize"],
            allowed_tools=["read_document", "edit_document"],
        ),
        PhaseDefinition(
            name=Phase.COMPLETE,
            description="Writing complete",
            required_steps=[],
        ),
    ],
)


MATH_WORKFLOW = WorkflowDefinition(
    workflow_type=WorkflowType.MATH,
    name="Math Problem Solving Workflow",
    description="Structured workflow for mathematical problem solving",
    phases=[
        PhaseDefinition(
            name=Phase.DISCOVERY,
            description="Understand problem and identify approach",
            required_steps=[
                "parse_problem",
                "identify_concepts",
                "plan_approach",
            ],
            allowed_tools=["search_web", "calculator", "record_knowledge"],
        ),
        PhaseDefinition(
            name=Phase.PLANNING,
            description="Break down into steps",
            required_steps=["decompose_problem", "identify_formulas"],
            allowed_tools=["calculator", "create_document"],
        ),
        PhaseDefinition(
            name=Phase.EXECUTION,
            description="Solve step by step",
            required_steps=["solve_steps", "verify_intermediate"],
            allowed_tools=["calculator", "python_executor", "wolfram_alpha"],
        ),
        PhaseDefinition(
            name=Phase.REVIEW,
            description="Verify solution",
            required_steps=["check_answer", "verify_logic"],
            allowed_tools=["calculator", "python_executor"],
        ),
        PhaseDefinition(
            name=Phase.COMPLETE,
            description="Problem solved",
            required_steps=[],
        ),
    ],
)


# Registry of predefined workflows
WORKFLOW_REGISTRY: Dict[WorkflowType, WorkflowDefinition] = {
    WorkflowType.CODING: CODING_WORKFLOW,
    WorkflowType.RESEARCH: RESEARCH_WORKFLOW,
    WorkflowType.WRITING: WRITING_WORKFLOW,
    WorkflowType.MATH: MATH_WORKFLOW,
}


def get_workflow(workflow_type: WorkflowType) -> Optional[WorkflowDefinition]:
    """Get a predefined workflow by type."""
    return WORKFLOW_REGISTRY.get(workflow_type)


def create_dynamic_workflow(
    name: str,
    description: str,
    phases: List[Dict[str, Any]],
) -> WorkflowDefinition:
    """Create a dynamic workflow from LLM-generated specification.

    This allows the LLM to define its own workflow at runtime.

    Args:
        name: Workflow name
        description: What this workflow does
        phases: List of phase definitions as dicts

    Returns:
        WorkflowDefinition that can be executed
    """
    phase_defs = []
    for phase_dict in phases:
        phase_defs.append(
            PhaseDefinition(
                name=Phase(phase_dict.get("name", "execution")),
                description=phase_dict.get("description", ""),
                required_steps=phase_dict.get("required_steps", []),
                optional_steps=phase_dict.get("optional_steps", []),
                allowed_tools=phase_dict.get("allowed_tools", []),
            )
        )

    return WorkflowDefinition(
        workflow_type=WorkflowType.DYNAMIC,
        name=name,
        description=description,
        phases=phase_defs,
    )
