"""Log entry for work done on a project."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from airunner_services.database.base import BaseModel


class ProgressEntry(BaseModel):
    """Log entry for work done on a project."""

    __tablename__ = "progress_entries"

    id = Column(Integer, primary_key=True)
    project_id = Column(
        Integer,
        ForeignKey("project_states.id"),
        nullable=False,
        index=True,
    )
    session_id = Column(Integer, ForeignKey("session_states.id"), index=True)
    feature_id = Column(Integer, ForeignKey("project_features.id"))
    timestamp = Column(DateTime, default=datetime.utcnow)
    action = Column(Text, nullable=False)
    outcome = Column(Text)
    files_changed = Column(JSON, default=list)
    git_commit_hash = Column(String(64))
    tokens_used = Column(Integer, default=0)

    project = relationship("ProjectState", back_populates="progress_entries")
    session = relationship("SessionState", back_populates="progress_entries")

    def to_log_string(self) -> str:
        """Format the entry for human-readable logs."""
        timestamp = self.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        commit = (
            f" [{self.git_commit_hash[:7]}]" if self.git_commit_hash else ""
        )
        files = (
            f"\n  Files: {', '.join(self.files_changed)}"
            if self.files_changed
            else ""
        )
        return (
            f"[{timestamp}]{commit} {self.action}\n"
            f"  Outcome: {self.outcome}{files}"
        )
