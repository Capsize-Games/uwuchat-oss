"""ItchConnection — linked itch.io accounts stored per user."""

from __future__ import annotations


from sqlalchemy import Column, DateTime, Integer, String, Text

from airunner_services.database.base import BaseModel


class ItchConnection(BaseModel):
    """One itch.io account linked to a UwUchat user."""

    __tablename__ = "itch_connections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, nullable=False, unique=True, index=True)
    itch_user_id = Column(Integer, nullable=True)
    username = Column(String(255), nullable=True)
    display_name = Column(String(255), nullable=True)
    cover_url = Column(String(512), nullable=True)
    profile_url = Column(String(512), nullable=True)
    owned_games_json = Column(Text, nullable=True)
    last_scraped_at = Column(DateTime, nullable=True)
    error = Column(String(512), nullable=True)

    @property
    def status(self) -> str:
        """Derive connection status from the stored data."""
        if self.error is not None:
            return "error"
        return "connected"


__all__ = ["ItchConnection"]
