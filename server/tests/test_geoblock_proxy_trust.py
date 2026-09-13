"""Tests for trusted-proxy IP resolution in geoblock.

Part 6 (MEDIUM) — ``X-Forwarded-For`` and ``X-Real-IP`` headers must
only be honoured when the immediate peer is a known trusted proxy.
A spoofed header from an untrusted peer must be ignored.

Also covers the expanded ``_is_private_ip`` ranges (169.254.0.0/16,
IPv6 private/link-local).
"""

from __future__ import annotations

from unittest.mock import MagicMock

from extensions.auth.server.geoblock import (
    _extract_client_ip,
    _is_private_ip,
    _is_trusted_proxy,
)


class TestIsTrustedProxy:
    """``_is_trusted_proxy`` identifies trusted proxy IPs."""

    def test_docker_private_ip_is_trusted(self) -> None:
        """A 10.x.x.x Docker private IP is trusted by default."""
        assert _is_trusted_proxy("10.0.0.1") is True

    def test_docker_bridge_ip_is_trusted(self) -> None:
        """A 172.x.x.x Docker bridge IP is trusted by default."""
        assert _is_trusted_proxy("172.17.0.1") is True

    def test_public_ip_is_not_trusted(self) -> None:
        """A public IP is not trusted."""
        assert _is_trusted_proxy("8.8.8.8") is False

    def test_invalid_ip_is_not_trusted(self) -> None:
        """An unparseable IP is not trusted."""
        assert _is_trusted_proxy("not-an-ip") is False


class TestExtractClientIpProxyTrust:
    """``_extract_client_ip`` ignores forwarded headers from untrusted
    peers."""

    def test_trusted_peer_honours_x_forwarded_for(self) -> None:
        """When the peer is a trusted proxy, X-Forwarded-For is used."""
        req = MagicMock()
        req.client.host = "10.0.0.1"  # trusted (within 10.0.0.0/8)
        req.headers = {"x-forwarded-for": "1.2.3.4, 10.0.0.1"}
        assert _extract_client_ip(req) == "1.2.3.4"

    def test_untrusted_peer_ignores_x_forwarded_for(self) -> None:
        """When the peer is NOT trusted, X-Forwarded-For is ignored."""
        req = MagicMock()
        req.client.host = "203.0.113.42"  # public, untrusted
        req.headers = {"x-forwarded-for": "1.2.3.4"}
        # Must fall back to the peer's real IP
        assert _extract_client_ip(req) == "203.0.113.42"

    def test_untrusted_peer_ignores_x_real_ip(self) -> None:
        """Untrusted peer's X-Real-IP is also ignored."""
        req = MagicMock()
        req.client.host = "198.51.100.1"  # untrusted
        req.headers = {"x-real-ip": "5.6.7.8"}
        assert _extract_client_ip(req) == "198.51.100.1"

    def test_no_peer_returns_none(self) -> None:
        """No client and no trusted proxy → None."""
        req = MagicMock()
        req.client = None
        req.headers = {"x-forwarded-for": "1.2.3.4"}
        assert _extract_client_ip(req) is None


class TestIsPrivateIpExtended:
    """``_is_private_ip`` covers additional ranges."""

    def test_ipv4_link_local(self) -> None:
        """169.254.x.x link-local is private."""
        assert _is_private_ip("169.254.1.1") is True
        assert _is_private_ip("169.254.255.255") is True

    def test_ipv6_loopback(self) -> None:
        """::1 is private."""
        assert _is_private_ip("::1") is True

    def test_ipv6_link_local(self) -> None:
        """fe80::/10 is private."""
        assert _is_private_ip("fe80::1") is True
        assert _is_private_ip("fe80::abcd:1234:5678") is True

    def test_ipv6_unique_local(self) -> None:
        """fc00::/7 (unique local) is private."""
        assert _is_private_ip("fc00::1") is True
        assert _is_private_ip("fdff::1") is True

    def test_ipv6_public_is_not_private(self) -> None:
        """A public IPv6 address is not private."""
        assert _is_private_ip("2a00:1450:4001:802::200e") is False

    def test_existing_ipv4_ranges_still_covered(self) -> None:
        """Existing private ranges are still detected."""
        assert _is_private_ip("10.0.0.1") is True
        assert _is_private_ip("127.0.0.1") is True
        assert _is_private_ip("172.16.0.1") is True
        assert _is_private_ip("192.168.1.1") is True
        assert _is_private_ip("8.8.8.8") is False
