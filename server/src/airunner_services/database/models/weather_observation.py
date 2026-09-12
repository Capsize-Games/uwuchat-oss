"""Anonymous, cross-tenant historical weather observations.

Every real (non-cached) Open-Meteo fetch produces one row in the ``public``
schema.  Contains no PII and no foreign keys back to any user/account/chatbot
table.

Coordinate precision is rounded to 2 decimal places (~1.1km) to prevent the
table from functioning as a precise location log.
"""

from __future__ import annotations


from sqlalchemy import Column, DateTime, Float, Integer, String

from airunner_services.database.base import BaseModel


class WeatherObservation(BaseModel):
    """One anonymous weather observation at one point in time."""

    __tablename__ = "weather_observations"
    __public_schema__ = True
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    observed_at = Column(DateTime(timezone=True), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    temperature = Column(Float, nullable=True)
    precipitation = Column(Float, nullable=True)
    rain = Column(Float, nullable=True)
    snowfall = Column(Float, nullable=True)
    wind_speed = Column(Float, nullable=True)
    wind_gusts = Column(Float, nullable=True)
    weather_code = Column(Integer, nullable=True)
    unit_system = Column(String(16), nullable=True)
    source = Column(String(64), nullable=False, default="open-meteo")
