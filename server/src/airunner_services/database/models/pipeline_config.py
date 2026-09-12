"""DB-backed pipeline config overrides.

One row per pipeline key in the ``public`` schema (not per-tenant).
The ``overrides`` JSONB column stores partial config that is
deep-merged over framework defaults at runtime.
"""

from __future__ import annotations


from sqlalchemy import Column, Integer, String
from sqlalchemy.dialects.postgresql import JSONB

from airunner_services.database.base import BaseModel


class PipelineConfig(BaseModel):
    """Admin overrides for one pipeline key."""

    __tablename__ = "pipeline_config"
    __public_schema__ = True
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    pipeline_key = Column(String(64), unique=True, nullable=False)
    overrides = Column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    updated_by = Column(String(128), nullable=True)
