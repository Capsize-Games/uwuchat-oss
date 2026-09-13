"""OpenRouter model catalog cache.

Lives in the ``public`` schema.  Synced from OpenRouter's public API.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB

from airunner_services.database.base import BaseModel


class OpenRouterModel(BaseModel):
    """Cached OpenRouter model pricing and metadata."""

    __tablename__ = "openrouter_model"
    __public_schema__ = True
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_id = Column(String(256), unique=True, nullable=False)
    display_name = Column(String(256), nullable=True)
    input_price_per_mtok = Column(
        Numeric(20, 8), nullable=True, default=0
    )
    output_price_per_mtok = Column(
        Numeric(20, 8), nullable=True, default=0
    )
    cache_read_per_mtok = Column(
        Numeric(20, 8), nullable=True, default=0
    )
    context_length = Column(Integer, nullable=True)
    latency_p50_ms = Column(Integer, nullable=True)
    throughput_tps = Column(Numeric(10, 2), nullable=True)
    providers_json = Column(JSONB, nullable=False, default=list)
    fetched_at = Column(
        DateTime, nullable=False, default=datetime.utcnow
    )
