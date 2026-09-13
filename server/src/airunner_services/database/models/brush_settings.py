"""Service-owned brush settings model."""

from sqlalchemy import Column, Integer, String

from airunner_services.settings import (
    AIRUNNER_DEFAULT_BRUSH_PRIMARY_COLOR,
    AIRUNNER_DEFAULT_BRUSH_SECONDARY_COLOR,
)
from airunner_services.database.base import BaseModel


class BrushSettings(BaseModel):
    """Persist canvas brush defaults and strength settings."""

    __tablename__ = "brush_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    size = Column(Integer, default=75)
    primary_color = Column(
        String,
        default=AIRUNNER_DEFAULT_BRUSH_PRIMARY_COLOR,
    )
    secondary_color = Column(
        String,
        default=AIRUNNER_DEFAULT_BRUSH_SECONDARY_COLOR,
    )
    strength_slider = Column(Integer, default=950)

    # Relationship to CanvasLayer disabled — enabling it triggers a
    # SQLAlchemy registry resolution error because BrushSettings and
    # CanvasLayer live in separate model modules and the relationship
    # references a class that may not be registered yet at import time.
    # Fix: either consolidate both models into a single module, use a
    # late-binding string reference with the full dotted path, or
    # restructure the model loader to guarantee registration order.
    # layer = relationship("CanvasLayer", back_populates="brush_settings")
    strength = Column(Integer, default=950)
    conditioning_scale = Column(Integer, default=550)
    guidance_scale = Column(Integer, default=75)


__all__ = ["BrushSettings"]
