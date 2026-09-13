"""Unit tests for send_mattermost_message."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from projects.uwuchat.server.tools import mattermost_tools as m

AGENT = SimpleNamespace(user=SimpleNamespace(is_superuser=True))
NON_ADMIN_AGENT = SimpleNamespace(user=SimpleNamespace(is_superuser=False))

_CONFIG = {
    "url": "https://mattermost.example.com",
    "token": "tok",
    "team": "team1",
    "default_channel": "town-square",
}


def test_non_superuser_is_declined() -> None:
    result = m.send_mattermost_message(
        message="hi", agent=NON_ADMIN_AGENT,
    )
    assert "admin-only" in result


def test_no_agent_is_declined() -> None:
    result = m.send_mattermost_message(message="hi", agent=None)
    assert "admin-only" in result


def test_blank_message_is_rejected() -> None:
    result = m.send_mattermost_message(message="   ", agent=AGENT)
    assert "need actual message text" in result


def test_missing_config_reports_not_configured() -> None:
    with patch.object(m, "_mattermost_config", return_value=None):
        result = m.send_mattermost_message(message="hi", agent=AGENT)
    assert "isn't configured" in result


def test_no_channel_and_no_default_is_rejected() -> None:
    config = dict(_CONFIG, default_channel="")
    with patch.object(m, "_mattermost_config", return_value=config):
        result = m.send_mattermost_message(message="hi", agent=AGENT)
    assert "No channel given" in result


def test_successful_post_uses_default_channel() -> None:
    driver = MagicMock()
    driver.channels.get_channel_by_name_and_team_name.return_value = {
        "id": "chan-1",
    }
    with patch.object(
        m, "_mattermost_config", return_value=_CONFIG,
    ), patch.object(m, "_build_driver", return_value=driver):
        result = m.send_mattermost_message(message="hello", agent=AGENT)
    driver.posts.create_post.assert_called_once_with(
        options={"channel_id": "chan-1", "message": "hello"},
    )
    assert "town-square" in result


def test_explicit_channel_overrides_default() -> None:
    driver = MagicMock()
    driver.channels.get_channel_by_name_and_team_name.return_value = {
        "id": "chan-2",
    }
    with patch.object(
        m, "_mattermost_config", return_value=_CONFIG,
    ), patch.object(m, "_build_driver", return_value=driver):
        result = m.send_mattermost_message(
            message="hello", channel="off-topic", agent=AGENT,
        )
    driver.channels.get_channel_by_name_and_team_name.assert_called_once_with(
        "team1", "off-topic",
    )
    assert "off-topic" in result


def test_driver_failure_is_reported_without_raising() -> None:
    with patch.object(
        m, "_mattermost_config", return_value=_CONFIG,
    ), patch.object(
        m, "_build_driver", side_effect=RuntimeError("boom"),
    ):
        result = m.send_mattermost_message(message="hello", agent=AGENT)
    assert "Couldn't post" in result
