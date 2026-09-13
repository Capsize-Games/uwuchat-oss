"""Join table linking knowledge facts to tags."""

from sqlalchemy import Column, ForeignKey, Integer, UniqueConstraint

from airunner_services.database.base import BaseModel


class KnowledgeFactTag(BaseModel):
    """Many-to-many association between KnowledgeFact and KnowledgeTag."""

    __tablename__ = "knowledge_fact_tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fact_id = Column(
        Integer,
        ForeignKey("knowledge_facts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tag_id = Column(
        Integer,
        ForeignKey("knowledge_tags.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        UniqueConstraint("fact_id", "tag_id", name="uq_knowledge_fact_tag"),
    )


__all__ = ["KnowledgeFactTag"]
