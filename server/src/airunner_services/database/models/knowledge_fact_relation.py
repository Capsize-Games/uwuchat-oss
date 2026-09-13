"""Typed fact-to-fact relationships (supersedes, follow_up, related).

Matches the precedent at knowledge_fact_tag.py.
"""
from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, String, UniqueConstraint

from airunner_services.database.base import BaseModel


class KnowledgeFactRelation(BaseModel):
    """One typed relationship between two KnowledgeFact rows."""

    __tablename__ = "knowledge_fact_relations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fact_id = Column(
        Integer,
        ForeignKey("knowledge_facts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    related_fact_id = Column(
        Integer,
        ForeignKey("knowledge_facts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    relation_type = Column(String(16), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "fact_id",
            "related_fact_id",
            "relation_type",
            name="uq_knowledge_fact_relation",
        ),
    )


__all__ = ["KnowledgeFactRelation"]
