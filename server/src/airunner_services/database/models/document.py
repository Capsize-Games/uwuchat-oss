"""Service-owned document registry model."""

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from airunner_services.database.base import BaseModel


class Document(BaseModel):
    """Persist document metadata for the knowledge base and indexing.

    ``chatbot_id`` is nullable — NULL means the document has not yet
    been scoped to a specific chatbot (e.g. historical rows from
    before per-chatbot scoping was introduced).  Documents with a NULL
    chatbot_id are excluded from all chat-turns until explicitly scoped.
    """

    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    path = Column(String, nullable=False, unique=True)
    active = Column(Boolean, default=True)
    indexed = Column(Boolean, default=False)
    index_uuid = Column(String, nullable=True, unique=True)
    file_hash = Column(String, nullable=True)
    indexed_at = Column(DateTime, nullable=True)
    file_size = Column(Integer, nullable=True)
    chatbot_id = Column(Integer, nullable=True, index=True)


__all__ = ["Document"]
