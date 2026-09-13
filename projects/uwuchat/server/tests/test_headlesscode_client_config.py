"""Unit tests for headlesscode_client's base-URL/token resolution.

Split out of test_headlesscode_client.py to stay under CLAUDE.md's
250-line file limit. Covers the env -> settings -> default resolution
order for both `_dashboard_url()` and `_bearer_token()`.
"""

from __future__ import annotations

import pytest

import projects.uwuchat.server.headlesscode_client as hc


def test_dashboard_url_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HEADLESSCODE_DASHBOARD_URL", "http://dash:9999/")
    assert hc._dashboard_url() == "http://dash:9999"


def test_dashboard_url_settings_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HEADLESSCODE_DASHBOARD_URL", raising=False)
    monkeypatch.setattr(
        hc.settings, "get", lambda name, default=None: "http://s:4390"
    )
    assert hc._dashboard_url() == "http://s:4390"


def test_dashboard_url_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HEADLESSCODE_DASHBOARD_URL", raising=False)
    monkeypatch.setattr(hc.settings, "get", lambda name, default=None: "")
    assert hc._dashboard_url() == "http://127.0.0.1:4390"


def test_bearer_token_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HEADLESSCODE_DASHBOARD_TOKEN", "  abc  ")
    assert hc._bearer_token() == "abc"


def test_bearer_token_settings_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HEADLESSCODE_DASHBOARD_TOKEN", raising=False)
    monkeypatch.setattr(hc.settings, "get", lambda name, default=None: "xyz")
    assert hc._bearer_token() == "xyz"


def test_bearer_token_default_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HEADLESSCODE_DASHBOARD_TOKEN", raising=False)
    monkeypatch.setattr(hc.settings, "get", lambda name, default=None: "")
    assert hc._bearer_token() == ""
