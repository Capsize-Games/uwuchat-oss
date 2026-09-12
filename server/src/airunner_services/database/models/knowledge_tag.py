"""Tag model for knowledge facts, scoped per chatbot agent."""

from sqlalchemy import Column, Integer, String, UniqueConstraint

from airunner_services.database.base import BaseModel


class KnowledgeTag(BaseModel):
    """A topic tag associated with knowledge facts for one chatbot agent."""

    __tablename__ = "knowledge_tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, index=True)
    chatbot_id = Column(Integer, nullable=True, index=True)

    __table_args__ = (
        UniqueConstraint(
            "name", "chatbot_id", name="uq_knowledge_tag_name_chatbot"
        ),
    )


__all__ = ["KnowledgeTag"]
