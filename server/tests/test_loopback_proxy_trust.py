"""Tests for proxy-aware client-IP loopback detection.

Part 1 (HIGH) — ``is_loopback_request()`` must read the real client IP
from ``X-Real-IP`` / ``X-Forwarded-For`` when ``AIRUNNER_BEHIND_PROXY=1``
rather than blindly trusting ``request.client.host`` (which is always the
proxy's own address behind a reverse proxy).
"""

from __future__ import annotations

from unittest.mock import MagicMock


def _make_request(
    client_host: str = "127.0.0.1",
    x_real_ip: str | None = None,
    x_forwarded_for: str | None = None,
) -> MagicMock:
    """Build a mock FastAPI Request with controllable peer and headers."""
    req = MagicMock()
    req.client = MagicMock()
    req.client.host = client_host
    headers: dict[str, str] = {}
    if x_real_ip is not None:
        headers["X-Real-IP"] = x_real_ip
    if x_forwarded_for is not None:
        headers["X-Forwarded-For"] = x_forwarded_for
    req.headers = headers
    return req


# ------------------------------------------------------------------
# _real_client_ip — direct (no proxy) mode
# ------------------------------------------------------------------


class TestRealClientIpDirect:
    """When AIRUNNER_BEHIND_PROXY is NOT set, behaviour is unchanged."""

    def test_direct_loopback(self, monkeypatch) -> None:
        """127.0.0.1 peer is treated as loopback in direct mode."""
        monkeypatch.delenv("AIRUNNER_BEHIND_PROXY", raising=False)
        # Force re-import so the module-level _BEHIND_PROXY is False.
        import airunner_services.api.server as srv

        import importlib

        importlib.reload(srv)

        req = _make_request(client_host="127.0.0.1")
        assert srv._real_client_ip(req) == "127.0.0.1"
        assert srv.is_loopback_request(req) is True

    def test_direct_remote(self, monkeypatch) -> None:
        """A non-loopback peer is NOT treated as loopback."""
        monkeypatch.delenv("AIRUNNER_BEHIND_PROXY", raising=False)
        import airunner_services.api.server as srv

        import importlib

        importlib.reload(srv)

        req = _make_request(client_host="203.0.113.42")
        assert srv._real_client_ip(req) == "203.0.113.42"
        assert srv.is_loopback_request(req) is False

    def test_direct_no_client(self, monkeypatch) -> None:
        """Missing client info returns False gracefully."""
        monkeypatch.delenv("AIRUNNER_BEHIND_PROXY", raising=False)
        import airunner_services.api.server as srv

        import importlib

        importlib.reload(srv)

        req = MagicMock()
        req.client = None
        req.headers = {}
        assert srv._real_client_ip(req) == ""
        assert srv.is_loopback_request(req) is False


# ------------------------------------------------------------------
# _real_client_ip — behind-proxy mode (AIRUNNER_BEHIND_PROXY=1)
# ------------------------------------------------------------------


class TestRealClientIpBehindProxy:
    """When AIRUNNER_BEHIND_PROXY=1, real IP is read from headers."""

    def _reload_with_proxy(self, monkeypatch):
        monkeypatch.setenv("AIRUNNER_BEHIND_PROXY", "1")
        import airunner_services.api.server as srv

        import importlib

        importlib.reload(srv)
        return srv

    def test_x_real_ip_takes_precedence(self, monkeypatch) -> None:
        """X-Real-IP is preferred over X-Forwarded-For."""
        srv = self._reload_with_proxy(monkeypatch)
        req = _make_request(
            client_host="127.0.0.1",  # proxy's IP
            x_real_ip="203.0.113.42",
            x_forwarded_for="198.51.100.1",
        )
        assert srv._real_client_ip(req) == "203.0.113.42"

    def test_x_forwarded_for_rightmost(self, monkeypatch) -> None:
        """Rightmost X-Forwarded-For entry is used (hardest to spoof)."""
        srv = self._reload_with_proxy(monkeypatch)
        # Attacker spoofs leftmost; real client IP is rightmost.
        req = _make_request(
            client_host="127.0.0.1",
            x_forwarded_for="1.2.3.4, 203.0.113.42",
        )
        assert srv._real_client_ip(req) == "203.0.113.42"

    def test_spoofed_leftmost_not_trusted(self, monkeypatch) -> None:
        """An attacker-controlled leftmost entry must NOT be returned."""
        srv = self._reload_with_proxy(monkeypatch)
        # Classic spoof: attacker puts loopback in leftmost position.
        req = _make_request(
            client_host="127.0.0.1",
            x_forwarded_for="127.0.0.1, 203.0.113.42",
        )
        assert srv._real_client_ip(req) == "203.0.113.42"
        # And crucially, the request is NOT treated as loopback.
        assert srv.is_loopback_request(req) is False

    def test_real_loopback_behind_proxy(self, monkeypatch) -> None:
        """A genuinely local request behind proxy is still loopback."""
        srv = self._reload_with_proxy(monkeypatch)
        req = _make_request(
            client_host="127.0.0.1",
            x_real_ip="127.0.0.1",
        )
        assert srv._real_client_ip(req) == "127.0.0.1"
        assert srv.is_loopback_request(req) is True

    def test_falls_back_to_direct_when_no_headers(
        self, monkeypatch,
    ) -> None:
        """When proxy headers are absent, falls back to peer address."""
        srv = self._reload_with_proxy(monkeypatch)
        req = _make_request(client_host="203.0.113.42")
        assert srv._real_client_ip(req) == "203.0.113.42"
        assert srv.is_loopback_request(req) is False

    def test_invalid_ip_in_headers_is_skipped(self, monkeypatch) -> None:
        """A malformed IP in a proxy header is skipped safely."""
        srv = self._reload_with_proxy(monkeypatch)
        req = _make_request(
            client_host="127.0.0.1",
            x_real_ip="not-an-ip",
            x_forwarded_for="also-bad, 203.0.113.42",
        )
        # X-Real-IP is invalid → skipped.
        # X-Forwarded-For: "also-bad" is invalid → skipped,
        # "203.0.113.42" is valid → used.
        assert srv._real_client_ip(req) == "203.0.113.42"


# ------------------------------------------------------------------
# Trusted-proxy peer validation
# ------------------------------------------------------------------


class TestRealClientIpUntrustedPeer:
    """When AIRUNNER_BEHIND_PROXY=1 but the immediate TCP peer is NOT
    in the trusted-proxy set, forwarded headers must be ignored."""

    def _reload_with_proxy(self, monkeypatch):
        monkeypatch.setenv("AIRUNNER_BEHIND_PROXY", "1")
        import airunner_services.api.server as srv

        import importlib

        importlib.reload(srv)
        return srv

    def test_direct_connection_spoofed_x_real_ip_ignored(
        self, monkeypatch,
    ) -> None:
        """A direct connection (peer not in trusted set) that sends
        ``X-Real-IP: 127.0.0.1`` must NOT be treated as loopback.

        This is the exact bypass scenario: an attacker reaches the app
        directly (bypassing nginx) and spoofs the loopback header.
        """
        srv = self._reload_with_proxy(monkeypatch)
        # Peer 203.0.113.42 is NOT in the default trusted set
        # (127.0.0.1, ::1).  The spoofed X-Real-IP must be ignored.
        req = _make_request(
            client_host="203.0.113.42",
            x_real_ip="127.0.0.1",
        )
        assert srv._real_client_ip(req) == "203.0.113.42"
        assert srv.is_loopback_request(req) is False

    def test_direct_connection_spoofed_xff_ignored(
        self, monkeypatch,
    ) -> None:
        """Same bypass via X-Forwarded-For — must also be ignored."""
        srv = self._reload_with_proxy(monkeypatch)
        req = _make_request(
            client_host="203.0.113.42",
            x_forwarded_for="127.0.0.1",
        )
        assert srv._real_client_ip(req) == "203.0.113.42"
        assert srv.is_loopback_request(req) is False


class TestRealClientIpTrustedProxyNoHeaders:
    """When the peer IS a trusted proxy but sends no forwarded headers,
    the proxy's own IP is returned — which for a localhost proxy means
    the request will be treated as loopback.  This is the safe default:
    if the proxy is misconfigured (no X-Real-IP / X-Forwarded-For),
    we cannot magically determine the real client, so we fall back to
    the peer address."""

    def _reload_with_proxy(self, monkeypatch):
        monkeypatch.setenv("AIRUNNER_BEHIND_PROXY", "1")
        import airunner_services.api.server as srv

        import importlib

        importlib.reload(srv)
        return srv

    def test_trusted_proxy_no_forwarded_headers(
        self, monkeypatch,
    ) -> None:
        """Trusted proxy (127.0.0.1) with no forwarded headers returns
        the proxy's own IP.  This IS loopback — correct, because the
        request genuinely came from localhost and we have no way to
        determine the original client."""
        srv = self._reload_with_proxy(monkeypatch)
        req = _make_request(
            client_host="127.0.0.1",
            # No X-Real-IP, no X-Forwarded-For
        )
        assert srv._real_client_ip(req) == "127.0.0.1"
        assert srv.is_loopback_request(req) is True


class TestRealClientIpTrustedProxyRegression:
    """Regression checks: when the peer IS a trusted proxy, forwarded
    headers must still be correctly resolved (the legitimate case)."""

    def _reload_with_proxy(self, monkeypatch):
        monkeypatch.setenv("AIRUNNER_BEHIND_PROXY", "1")
        import airunner_services.api.server as srv

        import importlib

        importlib.reload(srv)
        return srv

    def test_trusted_proxy_x_real_ip_resolves_remote(
        self, monkeypatch,
    ) -> None:
        """Trusted proxy (127.0.0.1) with X-Real-IP set to a remote
        client resolves to that remote IP — the legitimate case."""
        srv = self._reload_with_proxy(monkeypatch)
        req = _make_request(
            client_host="127.0.0.1",
            x_real_ip="203.0.113.42",
        )
        assert srv._real_client_ip(req) == "203.0.113.42"
        assert srv.is_loopback_request(req) is False


# ------------------------------------------------------------------
# is_loopback_host — unit
# ------------------------------------------------------------------


class TestIsLoopbackHost:
    """Unit tests for the pure string→bool helper."""

    def test_empty(self) -> None:
        from airunner_services.api.server import is_loopback_host

        assert is_loopback_host("") is False

    def test_localhost_variants(self) -> None:
        from airunner_services.api.server import is_loopback_host

        assert is_loopback_host("localhost") is True
        assert is_loopback_host("127.0.0.1") is True
        assert is_loopback_host("::1") is True

    def test_ipv4_loopback_range(self) -> None:
        from airunner_services.api.server import is_loopback_host

        assert is_loopback_host("127.0.0.2") is True
        assert is_loopback_host("127.255.255.255") is True

    def test_public_ip(self) -> None:
        from airunner_services.api.server import is_loopback_host

        assert is_loopback_host("203.0.113.1") is False
        assert is_loopback_host("8.8.8.8") is False
