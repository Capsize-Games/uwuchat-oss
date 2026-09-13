"""SteamConnection — linked Steam accounts stored per user."""

from __future__ import annotations


from sqlalchemy import Column, DateTime, Integer, String, Text

from airunner_services.database.base import BaseModel


class SteamConnection(BaseModel):
    """One Steam account linked to a UwUchat user."""

    __tablename__ = "steam_connections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, nullable=False, unique=True, index=True)
    steam_id = Column(String(64), nullable=False, unique=True)
    display_name = Column(String(255), nullable=True)
    avatar_url = Column(String(512), nullable=True)
    profile_url = Column(String(512), nullable=True)
    persona_state = Column(Integer, nullable=True)
    last_logoff = Column(DateTime, nullable=True)
    time_created = Column(DateTime, nullable=True)
    steam_level = Column(Integer, nullable=True)
    total_games_owned = Column(Integer, nullable=True)
    total_playtime_minutes = Column(Integer, nullable=True)
    friend_count = Column(Integer, nullable=True)
    top_games_json = Column(Text, nullable=True)
    all_games_json = Column(Text, nullable=True)
    recently_played_json = Column(Text, nullable=True)
    achievements_cache_json = Column(Text, nullable=True)
    last_scraped_at = Column(DateTime, nullable=True)
    error = Column(String(512), nullable=True)

    @property
    def status(self) -> str:
        """Derive connection status from the stored data."""
        if self.error is not None:
            return "error"
        return "connected"


__all__ = ["SteamConnection"]
