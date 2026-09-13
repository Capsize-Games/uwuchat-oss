"""State for a single agent session."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Text,
)
from sqlalchemy.orm import relationship

from airunner_services.database.base import BaseModel


class SessionState(BaseModel):
    """State for a single agent session."""

    __tablename__ = "session_states"

    id = Column(Integer, primary_key=True)
    project_id = Column(
        Integer,
        ForeignKey("project_states.id"),
        nullable=False,
        index=True,
    )
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime)
    feature_id = Column(Integer, ForeignKey("project_features.id"))
    context_snapshot = Column(JSON, default=dict)
    working_memory = Column(JSON, default=dict)
    last_action = Column(Text)
    next_recommended_action = Column(Text)
    error_state = Column(Text)
    tokens_consumed = Column(Integer, default=0)

    project = relationship("ProjectState", back_populates="sessions")
    progress_entries = relationship(
        "ProgressEntry",
        back_populates="session",
    )

    def get_context_for_next_session(self) -> dict:
        """Get context to seed the next session."""
        return {
            "previous_session_id": self.id,
            "last_action": self.last_action,
            "recommended_next": self.next_recommended_action,
            "working_memory": self.working_memory or {},
            "error_to_fix": self.error_state,
        }
