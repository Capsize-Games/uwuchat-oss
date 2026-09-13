"""Task & Goal REST API — read/write for the client panel."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from airunner_services.database.session import session_scope
from extensions.auth.server.dependencies import require_auth
from projects.uwuchat.server.models.task import Task
from projects.uwuchat.server.models.goal import Goal

router = APIRouter()


class GoalOut(BaseModel):
    """Serialised goal for the client."""
    id: int
    title: str
    description: Optional[str]
    target_date: Optional[str]
    status: str

    class Config:
        from_attributes = True


class TaskOut(BaseModel):
    """Serialised task for the client."""
    id: int
    title: str
    description: Optional[str]
    due_date: Optional[str]
    status: str
    goal_id: Optional[int]
    completed_at: Optional[str]

    class Config:
        from_attributes = True


class ProductivityOut(BaseModel):
    """Combined goals and tasks for the client panel."""
    goals: list[GoalOut]
    tasks: list[TaskOut]


@router.get("/", response_model=ProductivityOut)
async def list_productivity(
    account_id: int = Depends(require_auth),
) -> ProductivityOut:
    """Return all active goals and tasks for the authenticated user."""
    with session_scope() as session:
        goals = (
            session.query(Goal)
            .filter(
                Goal.user_id == account_id,
                Goal.deleted.is_(False),
            )
            .order_by(Goal.target_date.asc().nulls_last())
            .all()
        )
        tasks = (
            session.query(Task)
            .filter(
                Task.user_id == account_id,
                Task.deleted.is_(False),
            )
            .order_by(Task.due_date.asc().nulls_last())
            .all()
        )
    return ProductivityOut(
        goals=[_goal_to_out(g) for g in goals],
        tasks=[_task_to_out(t) for t in tasks],
    )


def _goal_to_out(row: Goal) -> GoalOut:
    """Map a Goal ORM row to the output schema."""
    return GoalOut(
        id=row.id,
        title=row.title,
        description=row.description,
        target_date=row.target_date.isoformat() if row.target_date else None,
        status=row.status,
    )


def _task_to_out(row: Task) -> TaskOut:
    """Map a Task ORM row to the output schema."""
    return TaskOut(
        id=row.id,
        title=row.title,
        description=row.description,
        due_date=row.due_date.isoformat() if row.due_date else None,
        status=row.status,
        goal_id=row.goal_id,
        completed_at=(
            row.completed_at.isoformat() if row.completed_at else None
        ),
    )
