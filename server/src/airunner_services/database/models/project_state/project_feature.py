"""A single feature in a long-running project."""

from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Column,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from airunner_services.database.base import BaseModel
from airunner_services.database.models.project_state.feature_category import (
    FeatureCategory,
)
from airunner_services.database.models.project_state.feature_status import (
    FeatureStatus,
)

if TYPE_CHECKING:
    from airunner_services.database.models.project_state.project_state import (
        ProjectState,
    )


class ProjectFeature(BaseModel):
    """A single feature in a long-running project."""

    __tablename__ = "project_features"

    id = Column(Integer, primary_key=True)
    project_id = Column(
        Integer,
        ForeignKey("project_states.id"),
        nullable=False,
        index=True,
    )
    name = Column(String(255), nullable=False)
    description = Column(Text)
    verification_steps = Column(JSON, default=list)
    category = Column(
        SQLEnum(FeatureCategory),
        default=FeatureCategory.FUNCTIONAL,
    )
    status = Column(
        SQLEnum(FeatureStatus),
        default=FeatureStatus.NOT_STARTED,
    )
    priority = Column(Integer, default=5)
    depends_on = Column(JSON, default=list)
    attempts = Column(Integer, default=0)
    last_error = Column(Text)

    project = relationship(
        "ProjectState",
        back_populates="features",
        foreign_keys=[project_id],
    )

    def can_work_on(self, project: "ProjectState") -> bool:
        """Check whether the feature's dependencies are satisfied."""
        if not self.depends_on:
            return True

        for dep_id in self.depends_on:
            for feature in project.features:
                if (
                    feature.id == dep_id
                    and feature.status != FeatureStatus.PASSING
                ):
                    return False
        return True

    def to_dict(self) -> dict:
        """Export the feature for agent context."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category.value if self.category else None,
            "status": self.status.value if self.status else None,
            "priority": self.priority,
            "verification_steps": self.verification_steps or [],
            "attempts": self.attempts,
            "last_error": self.last_error,
        }
