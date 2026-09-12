"""Tests for the geoblock module.

Covers: blocked-country IP detection, allowed-country IP detection,
private IPs bypassing the check, X-Forwarded-For header handling,
and empty/unset IP handling.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


from extensions.auth.server.geoblock import (
    _extract_client_ip,
    _is_private_ip,
    _lookup_country,
    blocked_country_codes,
)


class TestBlockedCountryCodes:
    """blocked_country_codes() parses config correctly."""

    def test_default_includes_eu_and_uk(self) -> None:
        """Default blocked list includes EU members and UK."""
        codes = blocked_country_codes()
        assert "GB" in codes
        assert "DE" in codes
        assert "FR" in codes

    def test_default_includes_eea(self) -> None:
        """Default blocked list includes EEA non-EU states."""
        codes = blocked_country_codes()
        assert "NO" in codes
        assert "IS" in codes
        assert "LI" in codes

    def test_default_includes_other_gdpr_equivalent_jurisdictions(
        self,
    ) -> None:
        """Default blocked list includes non-EEA jurisdictions with a
        GDPR-equivalent special-category-data regime."""
        codes = blocked_country_codes()
        assert "CH" in codes  # Switzerland — revised FADP
        assert "KR" in codes  # South Korea — PIPA
        assert "BR" in codes  # Brazil — LGPD
        assert "CN" in codes  # China — PIPL

    def test_default_excludes_consent_based_jurisdictions(self) -> None:
        """Japan, India, and Canada are consent-based regimes without
        a GDPR-style default prohibition — handled via a consent flow
        at registration, not a hard geoblock."""
        codes = blocked_country_codes()
        assert "JP" not in codes  # Japan — APPI
        assert "IN" not in codes  # India — DPDP Act
        assert "CA" not in codes  # Canada — PIPEDA

    @patch.dict("os.environ", {"AIRUNNER_BLOCKED_COUNTRY_CODES": "RU,CN"})
    def test_custom_env_var_overrides_default(self) -> None:
        """Setting AIRUNNER_BLOCKED_COUNTRY_CODES overrides the default."""
        codes = blocked_country_codes()
        assert "RU" in codes
        assert "CN" in codes
        assert "GB" not in codes
        assert "DE" not in codes


class TestIsPrivateIp:
    """_is_private_ip correctly identifies private/reserved IPs."""

    def test_loopback(self) -> None:
        assert _is_private_ip("127.0.0.1") is True

    def test_private_10(self) -> None:
        assert _is_private_ip("10.0.0.1") is True

    def test_private_172(self) -> None:
        assert _is_private_ip("172.16.0.1") is True
        assert _is_private_ip("172.31.255.255") is True

    def test_private_192(self) -> None:
        assert _is_private_ip("192.168.1.1") is True

    def test_public_ip(self) -> None:
        assert _is_private_ip("8.8.8.8") is False
        assert _is_private_ip("1.1.1.1") is False

    def test_invalid_ip(self) -> None:
        assert _is_private_ip("not-an-ip") is False


class TestLookupCountryRejectsMalformedIp:
    """_lookup_country must not embed unvalidated input in the
    ip-api.com request URL.

    ``ip`` ultimately comes from the client-supplied
    X-Forwarded-For header, so a malformed value (path-injection
    attempt, non-IP garbage) must be rejected before any URL is
    built or fetched -- not silently passed through.
    """

    @patch("extensions.auth.server.geoblock.urlopen")
    def test_malformed_ip_never_reaches_urlopen(
        self, mock_urlopen: MagicMock,
    ) -> None:
        result = _lookup_country("1.2.3.4/../admin?evil=1")
        assert result is None
        mock_urlopen.assert_not_called()

    @patch("extensions.auth.server.geoblock.urlopen")
    def test_non_ip_string_never_reaches_urlopen(
        self, mock_urlopen: MagicMock,
    ) -> None:
        result = _lookup_country("not-an-ip-at-all")
        assert result is None
        mock_urlopen.assert_not_called()

    @patch("extensions.auth.server.geoblock.urlopen")
    def test_valid_ip_still_reaches_urlopen(
        self, mock_urlopen: MagicMock,
    ) -> None:
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"countryCode": "US"}'
        mock_urlopen.return_value = mock_resp

        result = _lookup_country("8.8.8.8")
        assert result == "US"
        mock_urlopen.assert_called_once()


class TestExtractClientIp:
    """_extract_client_ip resolves the real client IP correctly."""

    def _make_request(self, headers: dict | None = None) -> MagicMock:
        """Build a minimal FastAPI-like request mock."""
        req = MagicMock()
        req.client = MagicMock()
        req.client.host = "10.0.0.1"
        req.headers = headers or {}
        return req

    def test_falls_back_to_client_host(self) -> None:
        """Without forwarding headers, uses request.client.host."""
        req = self._make_request({})
        assert _extract_client_ip(req) == "10.0.0.1"

    def test_x_forwarded_for_is_preferred(self) -> None:
        """X-Forwarded-For overrides request.client.host."""
        req = self._make_request({"x-forwarded-for": "1.2.3.4, 10.0.0.1"})
        assert _extract_client_ip(req) == "1.2.3.4"

    def test_x_real_ip_is_used(self) -> None:
        """X-Real-IP is used when X-Forwarded-For is absent."""
        req = self._make_request({"x-real-ip": "5.6.7.8"})
        assert _extract_client_ip(req) == "5.6.7.8"

    def test_no_client_returns_none(self) -> None:
        """When request.client is None, returns None."""
        req = MagicMock()
        req.client = None
        req.headers = {}
        assert _extract_client_ip(req) is None


class TestCheckGeoblock:
    """check_geoblock allows/blocks based on the client's country."""

    @patch("extensions.auth.server.geoblock._lookup_country")
    @patch("extensions.auth.server.geoblock.blocked_country_codes")
    async def test_blocked_country_returns_message(
        self, mock_codes: MagicMock, mock_lookup: MagicMock,
    ) -> None:
        """A blocked country returns a user-facing message."""
        mock_codes.return_value = frozenset({"DE"})
        mock_lookup.return_value = "DE"
        req = MagicMock()
        req.client.host = "1.2.3.4"
        req.headers = {}

        from extensions.auth.server.geoblock import check_geoblock

        msg = await check_geoblock(req)
        assert msg is not None
        assert "not available in your region" in msg

    @patch("extensions.auth.server.geoblock._lookup_country")
    async def test_allowed_country_returns_none(
        self, mock_lookup: MagicMock,
    ) -> None:
        """An allowed country returns None."""
        mock_lookup.return_value = "US"
        req = MagicMock()
        req.client.host = "1.2.3.4"
        req.headers = {}

        from extensions.auth.server.geoblock import check_geoblock

        msg = await check_geoblock(req)
        assert msg is None

    async def test_private_ip_returns_none(self) -> None:
        """A private IP bypasses geoblock."""
        req = MagicMock()
        req.client.host = "10.0.0.5"
        req.headers = {}

        from extensions.auth.server.geoblock import check_geoblock

        msg = await check_geoblock(req)
        assert msg is None

    async def test_no_client_ip_returns_none(self) -> None:
        """No client IP bypasses geoblock."""
        req = MagicMock()
        req.client = None
        req.headers = {}

        from extensions.auth.server.geoblock import check_geoblock

        msg = await check_geoblock(req)
        assert msg is None
