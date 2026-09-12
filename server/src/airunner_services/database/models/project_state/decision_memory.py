"""Memory of past decisions and their outcomes."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Enum as SQLEnum,
    Float,
    ForeignKey,
    Integer,
    Text,
)
from sqlalchemy.orm import relationship

from airunner_services.database.base import BaseModel
from airunner_services.database.models.project_state.decision_outcome import (
    DecisionOutcome,
)


class DecisionMemory(BaseModel):
    """Memory of past decisions and their outcomes."""

    __tablename__ = "decision_memories"

    id = Column(Integer, primary_key=True)
    project_id = Column(
        Integer,
        ForeignKey("project_states.id"),
        nullable=False,
        index=True,
    )
    feature_id = Column(Integer, ForeignKey("project_features.id"))
    timestamp = Column(DateTime, default=datetime.utcnow)
    decision_context = Column(Text, nullable=False)
    decision_made = Column(Text, nullable=False)
    reasoning = Column(Text)
    outcome = Column(SQLEnum(DecisionOutcome))
    outcome_score = Column(Float, default=0.0)
    lesson_learned = Column(Text)
    tags = Column(JSON, default=list)

    project = relationship("ProjectState", back_populates="decisions")

    def to_context_string(self) -> str:
        """Format the decision for agent context."""
        outcome_str = self.outcome.value if self.outcome else "pending"
        return (
            f"Decision: {self.decision_made}\n"
            f"Context: {self.decision_context}\n"
            f"Outcome: {outcome_str} (score: {self.outcome_score:.2f})\n"
            f"Lesson: {self.lesson_learned or 'None recorded'}"
        )
