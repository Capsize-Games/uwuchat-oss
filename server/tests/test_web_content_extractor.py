"""Regression tests for scraper blocklist behaviour in WebContentExtractor.

Covers the fixes from the scrape-website-blocklist-regression-fix plan:
1. FastSearch returning no content does NOT blocklist
2. Single transient fetch failures do NOT blocklist
3. Repeated failures DO blocklist after threshold
4. Blocklist entries expire after TTL
5. Successful fetch resets the failure counter

Updated 2026-07-08: tests now mock ``_call_fastsearch_scrape``
instead of ``trafilatura`` and ``_safe_fetch_html``.
"""

from __future__ import annotations

import time
from contextlib import ExitStack
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Shared mock factories
# ---------------------------------------------------------------------------

_FS_PATH = (
    "airunner_services.tools.web_content_extractor."
    "WebContentExtractor._call_fastsearch_scrape"
)
_VUF_PATH = (
    "airunner_services.tools.web_content_extractor.validate_url_for_fetch"
)


def _make_fs_mock(
    content: str | None = "Extracted content",
    title: str | None = "Test Title",
    error: str | None = None,
) -> MagicMock:
    """Return a MagicMock standing in for _call_fastsearch_scrape."""
    mock = MagicMock()
    if error is not None or content is None:
        mock.return_value = (
            {"error": error or "no content", "url": ""}
            if content is None
            else None
        )
    else:
        mock.return_value = {
            "url": "https://example.com/",
            "title": title,
            "content": content,
            "word_count": len(content.split()) if content else 0,
        }
    return mock


def _make_fs_mock_no_content() -> MagicMock:
    """Return a FastSearch mock whose scrape returns no content."""
    return _make_fs_mock(content=None, error="fetch returned no content")


def _make_fs_mock_none() -> MagicMock:
    """Return a FastSearch mock that returns None (total failure)."""
    mock = MagicMock()
    mock.return_value = None
    return mock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reset_class_state() -> None:
    """Reset all mutable class-level state on WebContentExtractor."""
    from airunner_services.tools.web_content_extractor import (
        BLOCKLIST_FILE as _ORIG_BLOCKLIST_FILE,
        WebContentExtractor as WCE,
    )

    WCE._blocklist = None
    WCE._failure_counts.clear()
    WCE.BLOCKLIST_FILE = _ORIG_BLOCKLIST_FILE


@pytest.fixture(autouse=True)
def _clean_state() -> None:
    """Automatically reset class state before and after each test."""
    _reset_class_state()
    yield
    _reset_class_state()


# ---------------------------------------------------------------------------
# Test 1: FastSearch no-content response → no blocklist
# ---------------------------------------------------------------------------


class TestFastSearchNoContentDoesNotBlocklist:
    """A FastSearch response with empty content must NOT blocklist."""

    def test_no_content_does_not_add_to_blocklist(self):
        """FastSearch returns content=None — domain stays unblocked."""
        from airunner_services.tools.web_content_extractor import (
            WebContentExtractor as WCE,
        )

        with ExitStack() as stack:
            stack.enter_context(
                patch(_FS_PATH, _make_fs_mock_no_content())
            )
            stack.enter_context(patch(_VUF_PATH, return_value=None))
            mock_save = stack.enter_context(
                patch.object(WCE, "_save_blocklist")
            )

            result = WCE.fetch_and_extract_with_metadata_raw(
                "https://no-content.example.com/page", use_cache=False
            )

        assert result is None, "no content should return None"
        mock_save.assert_not_called()


# ---------------------------------------------------------------------------
# Test 2: single transient fetch failure → no blocklist
# ---------------------------------------------------------------------------


class TestSingleFetchFailureDoesNotBlocklist:
    """A single fetch failure must NOT blocklist the domain."""

    def test_single_failure_no_blocklist(self):
        """One FastSearch returning None → domain still accessible."""
        from airunner_services.tools.web_content_extractor import (
            WebContentExtractor as WCE,
        )

        with ExitStack() as stack:
            stack.enter_context(
                patch(_FS_PATH, _make_fs_mock_none())
            )
            stack.enter_context(patch(_VUF_PATH, return_value=None))
            mock_save = stack.enter_context(
                patch.object(WCE, "_save_blocklist")
            )

            result = WCE.fetch_and_extract_with_metadata_raw(
                "https://single-fail.example.com/page", use_cache=False
            )

        assert result is None
        mock_save.assert_not_called()

        # Domain must NOT be blocked.
        assert not WCE._is_blocked(
            "https://single-fail.example.com/page"
        )

    def test_two_failures_no_blocklist(self):
        """Two fetch failures (below threshold of 3) → no blocklist."""
        from airunner_services.tools.web_content_extractor import (
            WebContentExtractor as WCE,
        )

        with ExitStack() as stack:
            stack.enter_context(
                patch(_FS_PATH, _make_fs_mock_none())
            )
            stack.enter_context(patch(_VUF_PATH, return_value=None))
            mock_save = stack.enter_context(
                patch.object(WCE, "_save_blocklist")
            )

            for _ in range(2):
                WCE.fetch_and_extract_with_metadata_raw(
                    "https://two-fail.example.com/page", use_cache=False
                )

        mock_save.assert_not_called()
        assert not WCE._is_blocked(
            "https://two-fail.example.com/page"
        )


# ---------------------------------------------------------------------------
# Test 3: repeated failures → blocklist after threshold
# ---------------------------------------------------------------------------


class TestRepeatedFailuresBlocklist:
    """Three consecutive fetch failures must eventually blocklist."""

    def test_three_failures_blocklists(self):
        """Three fetch failures → domain is added to blocklist."""
        from airunner_services.tools.web_content_extractor import (
            WebContentExtractor as WCE,
        )

        with ExitStack() as stack:
            stack.enter_context(
                patch(_FS_PATH, _make_fs_mock_none())
            )
            stack.enter_context(patch(_VUF_PATH, return_value=None))
            mock_save = stack.enter_context(
                patch.object(WCE, "_save_blocklist")
            )

            for _ in range(3):
                WCE.fetch_and_extract_with_metadata_raw(
                    "https://three-fail.example.com/page",
                    use_cache=False,
                )

        mock_save.assert_called()
        assert WCE._is_blocked(
            "https://three-fail.example.com/page"
        )

    def test_fetch_and_extract_also_uses_threshold(self):
        """fetch_and_extract() also obeys the failure threshold."""
        from airunner_services.tools.web_content_extractor import (
            WebContentExtractor as WCE,
        )

        with ExitStack() as stack:
            stack.enter_context(
                patch(_FS_PATH, _make_fs_mock_none())
            )
            stack.enter_context(patch(_VUF_PATH, return_value=None))
            mock_save = stack.enter_context(
                patch.object(WCE, "_save_blocklist")
            )

            for _ in range(3):
                WCE.fetch_and_extract(
                    "https://fe-three-fail.example.com/page",
                    use_cache=False,
                )

        mock_save.assert_called()
        assert WCE._is_blocked(
            "https://fe-three-fail.example.com/page"
        )


# ---------------------------------------------------------------------------
# Test 4: blocklist TTL expiry
# ---------------------------------------------------------------------------


class TestBlocklistTTLExpiry:
    """Entries older than 24 h must be treated as expired."""

    def test_expired_entry_not_blocked(self, tmp_path):
        """Domain with timestamp > 24 h old → _is_blocked() returns
        False."""
        from airunner_services.tools.web_content_extractor import (
            WebContentExtractor as WCE,
        )

        old_ts = time.time() - 90000  # 25 hours ago
        blocklist_file = tmp_path / ".scraper_blocklist"
        blocklist_file.write_text(f"old.example.com|{old_ts}\n")

        WCE._blocklist = None
        WCE.BLOCKLIST_FILE = blocklist_file

        blocklist = WCE._load_blocklist()
        assert "old.example.com" not in blocklist
        assert not WCE._is_blocked("https://old.example.com/page")

    def test_recent_entry_still_blocked(self, tmp_path):
        """Domain with recent timestamp → still blocked."""
        from airunner_services.tools.web_content_extractor import (
            WebContentExtractor as WCE,
        )

        recent_ts = time.time() - 3600  # 1 hour ago
        blocklist_file = tmp_path / ".scraper_blocklist"
        blocklist_file.write_text(
            f"recent.example.com|{recent_ts}\n"
        )

        WCE._blocklist = None
        WCE.BLOCKLIST_FILE = blocklist_file

        blocklist = WCE._load_blocklist()
        assert "recent.example.com" in blocklist
        assert WCE._is_blocked("https://recent.example.com/page")

    def test_settings_domain_never_expires(self, tmp_path):
        """Settings-based entries (timestamp 0.0) never expire."""
        from airunner_services.tools.web_content_extractor import (
            WebContentExtractor as WCE,
        )

        blocklist_file = tmp_path / ".scraper_blocklist"
        blocklist_file.write_text("")

        WCE._blocklist = None
        WCE.BLOCKLIST_FILE = blocklist_file

        with patch(
            "airunner_services.tools.scraper_blocklist."
            "AIRUNNER_SCRAPER_BLACKLIST",
            ["settings-blocked.example.com"],
        ):
            blocklist = WCE._load_blocklist()

        assert "settings-blocked.example.com" in blocklist
        assert WCE._is_blocked(
            "https://settings-blocked.example.com/page"
        )

    def test_expired_entry_allows_retry(self, tmp_path):
        """After TTL expires, fetch should be allowed to retry."""
        from airunner_services.tools.web_content_extractor import (
            WebContentExtractor as WCE,
        )

        old_ts = time.time() - 90000
        blocklist_file = tmp_path / ".scraper_blocklist"
        blocklist_file.write_text(
            f"expired.example.com|{old_ts}\n"
        )

        WCE._blocklist = None
        WCE.BLOCKLIST_FILE = blocklist_file

        with ExitStack() as stack:
            stack.enter_context(
                patch(_FS_PATH, _make_fs_mock())
            )
            stack.enter_context(patch(_VUF_PATH, return_value=None))

            result = WCE.fetch_and_extract_with_metadata_raw(
                "https://expired.example.com/page"
            )

        assert result is not None
        assert result["content"] is not None

    def test_legacy_no_timestamp_still_blocked(self, tmp_path):
        """Legacy entries without timestamp are treated as still-
        blocked."""
        from airunner_services.tools.web_content_extractor import (
            WebContentExtractor as WCE,
        )

        blocklist_file = tmp_path / ".scraper_blocklist"
        blocklist_file.write_text("legacy.example.com\n")

        WCE._blocklist = None
        WCE.BLOCKLIST_FILE = blocklist_file

        blocklist = WCE._load_blocklist()
        assert "legacy.example.com" in blocklist
        assert WCE._is_blocked("https://legacy.example.com/page")


# ---------------------------------------------------------------------------
# Test 5: successful fetch resets failure count
# ---------------------------------------------------------------------------


class TestSuccessfulFetchResetsFailures:
    """A successful fetch after failures must reset the counter."""

    def test_success_resets_counter(self):
        """Two failures + success + one failure → domain NOT
        blocklisted."""
        from airunner_services.tools.web_content_extractor import (
            WebContentExtractor as WCE,
        )

        # First: two failures (below threshold).
        with ExitStack() as stack:
            stack.enter_context(
                patch(_FS_PATH, _make_fs_mock_none())
            )
            stack.enter_context(patch(_VUF_PATH, return_value=None))
            mock_save = stack.enter_context(
                patch.object(WCE, "_save_blocklist")
            )

            for _ in range(2):
                WCE.fetch_and_extract_with_metadata_raw(
                    "https://reset-counter.example.com/page",
                    use_cache=False,
                )

        mock_save.assert_not_called()

        # Then: one successful fetch resets the counter.
        with ExitStack() as stack:
            stack.enter_context(
                patch(_FS_PATH, _make_fs_mock())
            )
            stack.enter_context(patch(_VUF_PATH, return_value=None))

            result = WCE.fetch_and_extract_with_metadata_raw(
                "https://reset-counter.example.com/page",
                use_cache=False,
            )

        assert result is not None

        # Then: one more failure — should NOT trigger blocklist.
        with ExitStack() as stack:
            stack.enter_context(
                patch(_FS_PATH, _make_fs_mock_none())
            )
            stack.enter_context(patch(_VUF_PATH, return_value=None))
            mock_save2 = stack.enter_context(
                patch.object(WCE, "_save_blocklist")
            )

            WCE.fetch_and_extract_with_metadata_raw(
                "https://reset-counter.example.com/page",
                use_cache=False,
            )

        mock_save2.assert_not_called()
        assert not WCE._is_blocked(
            "https://reset-counter.example.com/page"
        )

    def test_fetch_and_extract_success_resets_counter(self):
        """fetch_and_extract() success also resets the failure
        counter."""
        from airunner_services.tools.web_content_extractor import (
            WebContentExtractor as WCE,
        )

        # Two failures.
        with ExitStack() as stack:
            stack.enter_context(
                patch(_FS_PATH, _make_fs_mock_none())
            )
            stack.enter_context(patch(_VUF_PATH, return_value=None))
            mock_save = stack.enter_context(
                patch.object(WCE, "_save_blocklist")
            )

            for _ in range(2):
                WCE.fetch_and_extract(
                    "https://fe-reset.example.com/page",
                    use_cache=False,
                )

        mock_save.assert_not_called()

        # Success resets counter.
        with ExitStack() as stack:
            stack.enter_context(
                patch(_FS_PATH, _make_fs_mock())
            )
            stack.enter_context(patch(_VUF_PATH, return_value=None))

            result = WCE.fetch_and_extract(
                "https://fe-reset.example.com/page", use_cache=False
            )

        assert result is not None

        # One more failure — should NOT blocklist.
        with ExitStack() as stack:
            stack.enter_context(
                patch(_FS_PATH, _make_fs_mock_none())
            )
            stack.enter_context(patch(_VUF_PATH, return_value=None))
            mock_save2 = stack.enter_context(
                patch.object(WCE, "_save_blocklist")
            )

            WCE.fetch_and_extract(
                "https://fe-reset.example.com/page", use_cache=False
            )

        mock_save2.assert_not_called()
        assert not WCE._is_blocked(
            "https://fe-reset.example.com/page"
        )


# ---------------------------------------------------------------------------
# Test: log message includes reason
# ---------------------------------------------------------------------------


class TestBlocklistReasonLogging:
    """_add_to_blocklist must log the reason category when provided."""

    def test_reason_in_blocklist_entry(self):
        """Blocklist entry is created with a reason for network
        errors."""
        from airunner_services.tools.web_content_extractor import (
            WebContentExtractor as WCE,
        )
        import ssl

        with patch.object(WCE, "_save_blocklist"):
            WCE._maybe_blocklist(
                "https://example.com/page",
                ssl.SSLError("certificate verify failed"),
            )

        assert WCE._is_blocked("https://example.com/page")


# ---------------------------------------------------------------------------
# Test: _classify_fastsearch_error
# ---------------------------------------------------------------------------


class TestClassifyFastSearchError:
    """_classify_fastsearch_error maps error strings correctly."""

    def test_timeout_maps_to_timeouterror(self):
        """'Request timed out' → TimeoutError."""
        from airunner_services.tools.web_content_extractor import (
            WebContentExtractor as WCE,
        )

        exc = WCE._classify_fastsearch_error("Request timed out")
        assert isinstance(exc, TimeoutError)

    def test_connection_error_maps_to_connectionerror(self):
        """'Could not connect to the URL' → ConnectionError."""
        from airunner_services.tools.web_content_extractor import (
            WebContentExtractor as WCE,
        )

        exc = WCE._classify_fastsearch_error(
            "Could not connect to the URL"
        )
        assert isinstance(exc, ConnectionError)

    def test_unknown_error_returns_none(self):
        """Unrecognized error → None (no fast-blocklist)."""
        from airunner_services.tools.web_content_extractor import (
            WebContentExtractor as WCE,
        )

        exc = WCE._classify_fastsearch_error(
            "API key required"
        )
        assert exc is None


# ---------------------------------------------------------------------------
# Test: _maybe_blocklist wired in fetch paths
# ---------------------------------------------------------------------------


class TestMaybeBlocklistWiredInFetch:
    """FastSearch target-site errors trigger _maybe_blocklist."""

    def test_connection_error_fast_blocklists_in_raw(self):
        """FastSearch 'Could not connect' → _maybe_blocklist called."""
        from airunner_services.tools.web_content_extractor import (
            WebContentExtractor as WCE,
        )

        fs_mock = _make_fs_mock(
            content=None, error="Could not connect to the URL"
        )

        with ExitStack() as stack:
            stack.enter_context(patch(_FS_PATH, fs_mock))
            stack.enter_context(patch(_VUF_PATH, return_value=None))
            mock_blocklist = stack.enter_context(
                patch.object(WCE, "_maybe_blocklist")
            )

            result = WCE.fetch_and_extract_with_metadata_raw(
                "https://conn-refused.example.com/page",
                use_cache=False,
            )

        assert result is None
        mock_blocklist.assert_called_once()

    def test_api_key_error_does_not_blocklist_in_raw(self):
        """FastSearch 'API key required' → _maybe_blocklist NOT called."""
        from airunner_services.tools.web_content_extractor import (
            WebContentExtractor as WCE,
        )

        fs_mock = _make_fs_mock(
            content=None, error="API key required"
        )

        with ExitStack() as stack:
            stack.enter_context(patch(_FS_PATH, fs_mock))
            stack.enter_context(patch(_VUF_PATH, return_value=None))
            mock_blocklist = stack.enter_context(
                patch.object(WCE, "_maybe_blocklist")
            )

            result = WCE.fetch_and_extract_with_metadata_raw(
                "https://api-key-error.example.com/page",
                use_cache=False,
            )

        assert result is None
        mock_blocklist.assert_not_called()

    def test_connection_error_fast_blocklists_in_fe(self):
        """fetch_and_extract also fast-blocklists on connection error."""
        from airunner_services.tools.web_content_extractor import (
            WebContentExtractor as WCE,
        )

        fs_mock = _make_fs_mock(
            content=None, error="Could not connect to the URL"
        )

        with ExitStack() as stack:
            stack.enter_context(patch(_FS_PATH, fs_mock))
            stack.enter_context(patch(_VUF_PATH, return_value=None))
            mock_blocklist = stack.enter_context(
                patch.object(WCE, "_maybe_blocklist")
            )

            result = WCE.fetch_and_extract(
                "https://fe-conn-refused.example.com/page",
                use_cache=False,
            )

        assert result is None
        mock_blocklist.assert_called_once()
