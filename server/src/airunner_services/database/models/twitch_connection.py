"""TwitchConnection — linked Twitch accounts stored per user."""

from __future__ import annotations


from sqlalchemy import Column, DateTime, Integer, String

from airunner_services.database.base import BaseModel


class TwitchConnection(BaseModel):
    """One Twitch account linked to a UwUchat user."""

    __tablename__ = "twitch_connections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, nullable=False, unique=True, index=True)
    twitch_id = Column(String(64), nullable=False, unique=True)
    display_name = Column(String(255), nullable=True)
    avatar_url = Column(String(512), nullable=True)
    email = Column(String(255), nullable=True)
    description = Column(String(512), nullable=True)
    last_scraped_at = Column(DateTime, nullable=True)
    error = Column(String(512), nullable=True)

    @property
    def status(self) -> str:
        """Derive connection status from the stored data."""
        if self.error is not None:
            return "error"
        return "connected"

    @property
    def connected(self) -> bool:
        """True when a connection is established (not in error)."""
        return self.error is None


__all__ = ["TwitchConnection"]
