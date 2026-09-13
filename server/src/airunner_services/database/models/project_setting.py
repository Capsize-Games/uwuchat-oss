"""Per-tenant project-level key/value settings."""

from sqlalchemy import Column, Integer, String

from airunner_services.database.base import BaseModel


class ProjectSetting(BaseModel):
    """Generic key/value store for project-level UI preferences.

    Each tenant schema holds its own rows so settings are scoped per user.
    """

    __tablename__ = "project_setting"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String, nullable=False)
    value = Column(String, nullable=True)


__all__ = ["ProjectSetting"]
