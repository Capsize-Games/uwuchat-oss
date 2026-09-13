"""Persistent state for a long-running agent project."""

from sqlalchemy import (
    JSON,
    Column,
    Enum as SQLEnum,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from airunner_services.database.base import BaseModel
from airunner_services.database.models.project_state.project_status import (
    ProjectStatus,
)


class ProjectState(BaseModel):
    """Persistent state for a long-running agent project."""

    __tablename__ = "project_states"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True, index=True)
    description = Column(Text)
    working_directory = Column(String(512))
    git_repo_path = Column(String(512))
    status = Column(
        SQLEnum(ProjectStatus),
        default=ProjectStatus.INITIALIZING,
    )
    total_features = Column(Integer, default=0)
    passing_features = Column(Integer, default=0)
    current_feature_id = Column(Integer)
    system_prompt = Column(Text)
    project_metadata = Column(
        JSON,
        default=dict,
    )

    features = relationship(
        "ProjectFeature",
        back_populates="project",
        foreign_keys="ProjectFeature.project_id",
        cascade="all, delete-orphan",
    )
    progress_entries = relationship(
        "ProgressEntry",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    sessions = relationship(
        "SessionState",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    decisions = relationship(
        "DecisionMemory",
        back_populates="project",
        cascade="all, delete-orphan",
    )

    def get_progress_summary(self) -> str:
        """Get a human-readable progress summary."""
        if self.total_features == 0:
            return "Project not yet initialized"
        pct = (self.passing_features / self.total_features) * 100
        return (
            f"{self.passing_features}/{self.total_features} features passing "
            f"({pct:.1f}%)"
        )

    def to_context_dict(self) -> dict:
        """Export key project info for agent context."""
        return {
            "project_name": self.name,
            "description": self.description,
            "status": self.status.value if self.status else None,
            "progress": self.get_progress_summary(),
            "working_directory": self.working_directory,
        }
