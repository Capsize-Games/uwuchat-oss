"""UwUChat-registered headlesscode project (project registry)."""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, String

from airunner_services.database.base import BaseModel


class HeadlesscodeProject(BaseModel):
    """A user-registered project that headlesscode may work on.

    One row per user-registered project (repo path/URL plus its
    workspace root).  The chatbot may only launch headlesscode
    sessions against projects present in this table.
    """

    __tablename__ = "headlesscode_projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    name = Column(String(255), nullable=False)
    repo_path = Column(String(512), nullable=False)
    workspace_root = Column(String(512), nullable=False)


__all__ = ["HeadlesscodeProject"]
