"""Unit tests for the headlesscode dashboard HTTP client.

Covers request shapes for every wrapped route (method, path, query
params, JSON body), bearer-token auth (sent when configured, absent
otherwise), the non-2xx -> ``HTTPStatusError`` contract, and the
base-URL/token resolution order (env -> settings -> default).
"""

from __future__ import annotations

import json

import httpx
import pytest

import projects.uwuchat.server.headlesscode_client as hc


class _FakeDashboard:
    """MockTransport-backed fake dashboard recording the last request."""

    def __init__(self) -> None:
        self.method = ""
        self.url = ""
        self.headers: dict[str, str] = {}
        self.body: str | None = None
        self.status = 200

    def handler(self, request: httpx.Request) -> httpx.Response:
        """Serve the fake dashboard's routes and record the request."""
        self.method = request.method
        self.url = str(request.url)
        self.headers = {
            key: value for key, value in request.headers.items()
        }
        self.body = (
            request.content.decode("utf-8") if request.content else None
        )
        if self.status != 200:
            return httpx.Response(self.status, json={"error": "boom"})
        if request.url.path == "/api/session/start":
            return httpx.Response(
                200,
                json={
                    "sessionId": "s-1",
                    "pid": 42,
                    "workspace": "/data/w",
                    "mode": "multi-agent-orchestrator-headless",
                },
            )
        if request.url.path.endswith("/events"):
            return httpx.Response(
                200,
                json={"sessionId": "s-1", "events": [], "nextOffset": 0},
            )
        return httpx.Response(
            200,
            json={"sessionId": "s-1", "ok": True, "worktree": "."},
        )


@pytest.fixture()
def fake_dashboard(monkeypatch: pytest.MonkeyPatch) -> _FakeDashboard:
    """Point the client's httpx.AsyncClient at a fake dashboard.

    Pins the base URL and token via env so resolution is deterministic
    regardless of the (cached) settings store.
    """
    fake = _FakeDashboard()
    monkeypatch.setenv(
        "HEADLESSCODE_DASHBOARD_URL", "http://127.0.0.1:4390"
    )
    monkeypatch.setenv("HEADLESSCODE_DASHBOARD_TOKEN", "secret")
    real_client = httpx.AsyncClient

    def _client(*args: object, **kwargs: object) -> httpx.AsyncClient:
        # Capture real_client before patching: referencing httpx.AsyncClient
        # here would recurse into this very stub.
        return real_client(
            transport=httpx.MockTransport(fake.handler),
            *args,
            **kwargs,
        )

    monkeypatch.setattr(httpx, "AsyncClient", _client)
    return fake


# ---------------------------------------------------------------------------
# POST /api/session/start — launch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_session_posts_launch(
    fake_dashboard: _FakeDashboard,
) -> None:
    result = await hc.start_session(
        repo="/data/w", task="fix the bug", mode="code"
    )
    assert fake_dashboard.method == "POST"
    assert fake_dashboard.url == (
        "http://127.0.0.1:4390/api/session/start"
    )
    assert json.loads(fake_dashboard.body or "{}") == {
        "repo": "/data/w",
        "task": "fix the bug",
        "mode": "code",
    }
    assert result["sessionId"] == "s-1"
    assert result["pid"] == 42


@pytest.mark.asyncio
async def test_start_session_omits_mode_when_absent(
    fake_dashboard: _FakeDashboard,
) -> None:
    await hc.start_session(repo="/data/w", task="hello")
    assert json.loads(fake_dashboard.body or "{}") == {
        "repo": "/data/w",
        "task": "hello",
    }


# ---------------------------------------------------------------------------
# GET /api/session/:id/events?since= — poll
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_session_events_polls_since(
    fake_dashboard: _FakeDashboard,
) -> None:
    result = await hc.get_session_events("s-1", "/data/w", since=7)
    assert fake_dashboard.method == "GET"
    assert "/api/session/s-1/events" in fake_dashboard.url
    assert "since=7" in fake_dashboard.url
    assert "repo=" in fake_dashboard.url
    assert result == {"sessionId": "s-1", "events": [], "nextOffset": 0}


# ---------------------------------------------------------------------------
# POST /api/session/:id/pause|resume|answer|message — control
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("call", "path", "expected_body"),
    [
        (
            lambda: hc.pause_session("s-1", "/data/w"),
            "/api/session/s-1/pause",
            {},
        ),
        (
            lambda: hc.resume_session("s-1", "/data/w"),
            "/api/session/s-1/resume",
            {},
        ),
        (
            lambda: hc.answer_session("s-1", "yes, go ahead", "/data/w"),
            "/api/session/s-1/answer",
            {"answer": "yes, go ahead"},
        ),
        (
            lambda: hc.message_session("s-1", "keep going", "/data/w"),
            "/api/session/s-1/message",
            {"text": "keep going"},
        ),
    ],
)
async def test_control_routes(
    fake_dashboard: _FakeDashboard,
    call,
    path: str,
    expected_body: dict,
) -> None:
    result = await call()
    assert fake_dashboard.method == "POST"
    assert fake_dashboard.url == (
        f"http://127.0.0.1:4390{path}?repo=%2Fdata%2Fw"
    )
    assert json.loads(fake_dashboard.body or "{}") == expected_body
    assert result["ok"] is True


# ---------------------------------------------------------------------------
# Bearer-token auth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bearer_token_sent_when_configured(
    fake_dashboard: _FakeDashboard,
) -> None:
    await hc.pause_session("s-1", "/data/w")
    assert fake_dashboard.headers.get("authorization") == "Bearer secret"


@pytest.mark.asyncio
async def test_no_bearer_token_when_unset(
    monkeypatch: pytest.MonkeyPatch,
    fake_dashboard: _FakeDashboard,
) -> None:
    monkeypatch.delenv("HEADLESSCODE_DASHBOARD_TOKEN", raising=False)
    monkeypatch.setattr(hc.settings, "get", lambda name, default=None: "")
    await hc.pause_session("s-1", "/data/w")
    assert "authorization" not in fake_dashboard.headers


# ---------------------------------------------------------------------------
# Error contract
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_2xx_raises_http_status_error(
    fake_dashboard: _FakeDashboard,
) -> None:
    fake_dashboard.status = 500
    with pytest.raises(httpx.HTTPStatusError):
        await hc.start_session(repo="/data/w", task="x")


# Base URL / token resolution tests live in
# test_headlesscode_client_config.py (kept separate to stay under
# CLAUDE.md's 250-line file limit).
