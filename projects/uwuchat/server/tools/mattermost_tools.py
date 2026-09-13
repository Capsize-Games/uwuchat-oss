"""LLM tool: send_mattermost_message — post to the homeserver Mattermost.

Uses the "uwuchat" bot account (see MATTERMOST_BOT_TOKEN in
projects/uwuchat/.env) via the mattermostdriver package. Admin-only for
now (real-world side effect, visible to other real Mattermost users) —
see _require_superuser.

All functions are <=20 lines.
"""

from __future__ import annotations

import logging
import os
from typing import Annotated, Any
from urllib.parse import urlsplit

from airunner_services.llm.core.tool_registry import ToolCategory, tool

logger = logging.getLogger(__name__)


def _env(name: str, default: str = "") -> str:
    """Return an env var, falling back to project settings, then default."""
    value = os.environ.get(name, "").strip()
    if value:
        return value
    from airunner_services.conf import settings

    return str(settings.get(name, "") or "").strip() or default


def _mattermost_config() -> dict[str, str] | None:
    """Return the configured Mattermost connection, or None if unset."""
    url = _env("MATTERMOST_URL")
    token = _env("MATTERMOST_BOT_TOKEN")
    if not url or not token:
        return None
    return {
        "url": url,
        "token": token,
        "team": _env("MATTERMOST_TEAM_NAME"),
        "default_channel": _env("MATTERMOST_DEFAULT_CHANNEL"),
    }


def _build_driver(config: dict[str, str]):
    """Return a logged-in mattermostdriver.Driver for *config*."""
    from mattermostdriver import Driver

    parts = urlsplit(config["url"])
    driver = Driver({
        "url": parts.hostname,
        "token": config["token"],
        "scheme": parts.scheme or "https",
        "port": parts.port or (443 if parts.scheme != "http" else 80),
    })
    driver.login()
    return driver


def _resolve_channel_id(driver, config: dict[str, str], channel: str) -> str:
    """Return the channel id for *channel* (name) in the configured team."""
    team = driver.teams.get_team_by_name(config["team"])
    ch = driver.channels.get_channel_by_name_and_team_name(
        config["team"], channel,
    )
    del team
    return ch["id"]


@tool(
    name="send_mattermost_message",
    category=ToolCategory.SYSTEM,
    description=(
        "Post a message to a channel on the team's Mattermost workspace "
        "(a real chat tool other people use, separate from UwUChat). "
        "Admin-only. Use when the user explicitly asks to post/send/"
        "notify something in Mattermost or a named channel there."
    ),
    return_direct=False,
    requires_agent=True,
    keywords=[
        "mattermost", "post to mattermost", "notify the team",
        "send a message to", "channel message",
    ],
    input_examples=[
        {"message": "Deploy finished successfully."},
        {"channel": "off-topic", "message": "Anyone around?"},
    ],
)
def send_mattermost_message(
    message: Annotated[str, "The message text to post."],
    channel: Annotated[
        str | None,
        "Channel name to post to. Omit for the configured default "
        "channel.",
    ] = None,
    agent: Any = None,
) -> str:
    """Post *message* to Mattermost; admin-only, best-effort errors."""
    user = getattr(agent, "user", None) if agent else None
    if not getattr(user, "is_superuser", False):
        return (
            "I can't post to Mattermost — that's an admin-only action."
        )
    if not message.strip():
        return "I need actual message text to post."
    config = _mattermost_config()
    if config is None:
        return (
            "Mattermost isn't configured on this server "
            "(MATTERMOST_URL / MATTERMOST_BOT_TOKEN missing)."
        )
    target_channel = (channel or config["default_channel"]).strip()
    if not target_channel:
        return "No channel given and no default channel is configured."
    try:
        driver = _build_driver(config)
        channel_id = _resolve_channel_id(driver, config, target_channel)
        driver.posts.create_post(options={
            "channel_id": channel_id,
            "message": message,
        })
    except Exception as exc:
        logger.warning(
            "Mattermost post failed: channel=%s err=%s",
            target_channel, type(exc).__name__,
        )
        return (
            f"Couldn't post to Mattermost channel '{target_channel}' — "
            "check the channel name and bot permissions."
        )
    return f"Posted to Mattermost #{target_channel}."
