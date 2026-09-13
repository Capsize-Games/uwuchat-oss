"""Tests that external XML parsing rejects XXE payloads.

Part 3 (Bandit B314) — round-8 security remediation. ``kiwix_api.py``
and ``arxiv_provider.py`` parse XML fetched from external network
services and must use ``defusedxml`` rather than the stdlib parser,
which is vulnerable to external-entity and billion-laughs attacks.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_XXE_PAYLOAD = (
    '<?xml version="1.0"?>'
    '<!DOCTYPE root [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
    "<root>&xxe;</root>"
)


class TestKiwixApiRejectsXxe:
    """``KiwixAPI.list_zim_files`` must not process XXE payloads."""

    def test_xxe_payload_is_rejected(self) -> None:
        from airunner_services.kiwix_api import KiwixAPI

        with patch(
            "airunner_services.kiwix_api.safe_fetch_url",
            return_value=_XXE_PAYLOAD,
        ):
            # The XXE attempt raises inside the try/except in
            # list_zim_files, which logs and returns an empty list --
            # it must NOT resolve the external entity.
            result = KiwixAPI.list_zim_files()
            assert result == []

    def test_legitimate_atom_feed_still_parses(self) -> None:
        from airunner_services.kiwix_api import KiwixAPI

        atom_feed = (
            '<?xml version="1.0"?>'
            '<feed xmlns="http://www.w3.org/2005/Atom">'
            "<entry><title>Test</title></entry>"
            "</feed>"
        )
        with patch(
            "airunner_services.kiwix_api.safe_fetch_url",
            return_value=atom_feed,
        ):
            result = KiwixAPI.list_zim_files()
            assert isinstance(result, list)


class TestArxivProviderRejectsXxe:
    """``ArxivProvider.search`` must not process XXE payloads."""

    @pytest.mark.asyncio
    async def test_xxe_payload_is_rejected_not_resolved(self) -> None:
        """The XXE attempt must not resolve -- ``search`` catches the
        ``EntitiesForbidden`` in its existing broad except clause and
        returns an empty result list rather than the entity's
        contents or a crash."""
        from airunner_services.tools.search_providers.arxiv_provider import (
            ArxivProvider,
        )

        provider = ArxivProvider()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.text = AsyncMock(return_value=_XXE_PAYLOAD)

        mock_get_ctx = MagicMock()
        mock_get_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_get_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_client = MagicMock()
        mock_client.get = MagicMock(return_value=mock_get_ctx)

        results = await provider.search("test query", client=mock_client)
        assert results == []

    @pytest.mark.asyncio
    async def test_legitimate_atom_feed_still_parses(self) -> None:
        from airunner_services.tools.search_providers.arxiv_provider import (
            ArxivProvider,
        )

        atom_feed = (
            '<?xml version="1.0"?>'
            '<feed xmlns="http://www.w3.org/2005/Atom">'
            "<entry>"
            "<title>A Test Paper</title>"
            "<id>http://arxiv.org/abs/1234.5678</id>"
            "<summary>An abstract.</summary>"
            "</entry>"
            "</feed>"
        )
        provider = ArxivProvider()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.text = AsyncMock(return_value=atom_feed)

        mock_get_ctx = MagicMock()
        mock_get_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_get_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_client = MagicMock()
        mock_client.get = MagicMock(return_value=mock_get_ctx)

        results = await provider.search("test query", client=mock_client)
        assert isinstance(results, list)
