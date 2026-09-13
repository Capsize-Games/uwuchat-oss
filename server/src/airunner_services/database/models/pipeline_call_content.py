"""Encrypted prompt/response text for one pipeline LLM call.

Lives in EACH TENANT'S OWN schema (unlike PipelineTokenUsage, which is
shared/public — see that model's docstring). Linked to its
PipelineTokenUsage row via ``usage_id``, which stores that row's ``id``
from the public schema. There is no cross-schema foreign key
constraint (Postgres cross-schema FKs across the tenant-per-schema
setup used here are not practical) — ``usage_id`` is a plain indexed
integer column that the API joins in application code, only after
confirming the requesting superuser owns the tenant schema being
queried.

Never queried directly from the LLM pipeline hot path — this exists
solely to back the superuser conversation-inspector panel.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Index, Integer

from airunner_services.database.base import BaseModel
from airunner_services.utils.crypto import UserEncryptedText


class PipelineCallContent(BaseModel):
    """Encrypted prompt/response text for one PipelineTokenUsage row."""

    __tablename__ = "pipeline_call_content"
    __table_args__ = (
        Index("ix_pcc_usage_id", "usage_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    usage_id = Column(Integer, nullable=False, index=True)
    prompt_text = Column(UserEncryptedText, nullable=True)
    response_text = Column(UserEncryptedText, nullable=True)
    created_at = Column(
        DateTime, nullable=False, default=datetime.utcnow
    )


__all__ = ["PipelineCallContent"]
