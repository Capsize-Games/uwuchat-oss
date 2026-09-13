"""Per-LLM-call token usage records.

Lives in the ``public`` schema.  Written fire-and-forget after every
pipeline LLM call so the admin dashboard can compute per-customer
cost estimates.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
)

from airunner_services.database.base import BaseModel


class PipelineTokenUsage(BaseModel):
    """One record per pipeline LLM call (including skipped calls)."""

    __tablename__ = "pipeline_token_usage"
    __public_schema__ = True
    __table_args__ = (
        Index("ix_ptu_key_recorded", "pipeline_key", "recorded_at"),
        Index(
            "ix_ptu_account_recorded",
            "account_id",
            "recorded_at",
        ),
        {"schema": "public"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    pipeline_key = Column(String(64), nullable=False)
    model_id = Column(String(256), nullable=False)
    chatbot_id = Column(Integer, nullable=True, index=True)
    call_chain_id = Column(String(36), nullable=True, index=True)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    cache_read_tokens = Column(Integer, nullable=False, default=0)
    tenant_key = Column(String(128), nullable=True, index=True)
    account_id = Column(Integer, nullable=True, index=True)
    recorded_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, index=True
    )
    skipped = Column(Boolean, nullable=False, default=False)
    complexity_score = Column(Numeric(5, 4), nullable=True)
    tier_name = Column(String(64), nullable=True)
    risk_score = Column(Numeric(5, 4), nullable=True)
    risk_tier = Column(String(16), nullable=True)
    prompt_tokens_saved = Column(Integer, nullable=True)
    prompt_char_count = Column(Integer, nullable=True)
    response_char_count = Column(Integer, nullable=True)
    input_price_per_mtok = Column(Numeric(20, 8), nullable=True)
    output_price_per_mtok = Column(Numeric(20, 8), nullable=True)
    cache_price_per_mtok = Column(Numeric(20, 8), nullable=True)
    cost_usd = Column(Numeric(20, 8), nullable=True, index=True)
