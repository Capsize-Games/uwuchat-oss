"""Service-owned user model."""

from sqlalchemy import Boolean, Column, Float, Integer, JSON, String, Text

from airunner_services.database.base import BaseModel


class User(BaseModel):
    """Persisted end-user profile data used by conversations and tools."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, nullable=False, default="User")
    zipcode = Column(String, nullable=True)
    location_display_name = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    unit_system = Column(String, nullable=True, default="imperial")
    preferred_language = Column(String, nullable=True, default="en")
    setup_complete = Column(Boolean, nullable=True, default=False)
    display_name = Column(String(100), nullable=True)
    gender = Column(String(20), nullable=True)
    data = Column(JSON, nullable=True)
    avatar_image = Column(Text, nullable=True)
    banner_image = Column(Text, nullable=True)


__all__ = ["User"]
