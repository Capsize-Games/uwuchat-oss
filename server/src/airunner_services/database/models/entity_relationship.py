"""EntityRelationship — edge between two entities in the knowledge graph.

Deliberately named ``entity_relationships`` to avoid collision with
the existing ``Relationship`` model (which tracks a chatbot's *felt*
warmth/trust toward users/bots — a roleplay mechanic, not a factual
network graph).
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    String,
    UniqueConstraint,
)

from airunner_services.database.base import BaseModel


class EntityRelationship(BaseModel):
    """One edge between two entities — built from email co-occurrence.

    Always stored with ``entity_a_id < entity_b_id`` (canonical
    ordering) to avoid duplicate edges in both directions.
    ``strength`` is a normalized function of ``evidence_count``.
    """

    __tablename__ = "entity_relationships"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_a_id = Column(Integer, nullable=False, index=True)
    entity_b_id = Column(Integer, nullable=False, index=True)
    relationship_type = Column(String(32), nullable=True)
    evidence_count = Column(Integer, nullable=False, default=0)
    strength = Column(Float, nullable=False, default=0.0)
    source = Column(
        String(32), nullable=False, default="email_co_occurrence",
    )
    first_observed_at = Column(DateTime, nullable=True)
    last_observed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "entity_a_id", "entity_b_id", "source",
            name="uq_entity_relationship_edge",
        ),
    )


__all__ = ["EntityRelationship"]
