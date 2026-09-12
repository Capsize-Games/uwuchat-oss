"""Scraper blocklist, TTL, and failure-threshold logic.

Extracted from ``web_content_extractor.py`` to keep that module under
the project's 250-line file cap.  ``WebContentExtractor`` inherits from
``ScraperBlocklistMixin`` to gain all blocklist-related methods.
"""

from __future__ import annotations

import socket
import ssl
import time
from typing import Dict, List, Optional, Set
from urllib.parse import urlparse

from airunner_services.settings import (
    AIRUNNER_LOG_LEVEL,
    AIRUNNER_SCRAPER_BLACKLIST,
)
from airunner_services.utils.application import get_logger
from airunner_services.utils.application.log_hygiene import fingerprint_value

__all__ = ["ScraperBlocklistMixin"]

_logger = get_logger(__name__, AIRUNNER_LOG_LEVEL)


class ScraperBlocklistMixin:
    """Mixin providing scraper blocklist, TTL, and failure-tracking.

    Classes that inherit from this mixin must define::

        BLOCKLIST_FILE: Path   # path to the on-disk blocklist file

    Class-level constants (overrideable)::

        _FAILURE_THRESHOLD: int = 3
        _FAILURE_WINDOW_SECONDS: float = 86400.0
        _BLOCKLIST_TTL_SECONDS: float = 86400.0
    """

    _blocklist: Optional[Dict[str, float]] = None
    _failure_counts: Dict[str, List[float]] = {}

    _FAILURE_THRESHOLD: int = 3
    _FAILURE_WINDOW_SECONDS: float = 86400.0  # 24 hours
    _BLOCKLIST_TTL_SECONDS: float = 86400.0  # 24 hours

    @classmethod
    def _get_base_url(cls, url: str) -> str:
        """Extract domain (netloc only) for blocklist matching."""
        parsed = urlparse(url)
        return parsed.netloc

    # -- blocklist I/O ---------------------------------------------------

    @classmethod
    def _load_blocklist(cls) -> Dict[str, float]:
        """Load the blocklist from file, merge with settings, apply TTL.

        File format: one entry per line, either ``domain`` (legacy,
        no timestamp) or ``domain|unix_timestamp``.

        Legacy and corrupt-timestamp entries are assigned *now* as
        their timestamp so they get one TTL window to auto-expire.
        ``0.0`` is reserved for settings-based
        (``AIRUNNER_SCRAPER_BLACKLIST``) entries, which never expire.
        """
        if cls._blocklist is not None:
            return cls._blocklist

        cls._blocklist = {}
        now = time.time()

        if cls.BLOCKLIST_FILE.exists():
            try:
                content = cls.BLOCKLIST_FILE.read_text(encoding="utf-8")
                loaded = 0
                expired = 0
                legacy = 0
                for line in content.splitlines():
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#"):
                        continue
                    raw = (
                        stripped.replace("http://", "")
                        .replace("https://", "")
                        .strip("/")
                    )
                    if "|" in raw:
                        domain, ts_str = raw.split("|", 1)
                        try:
                            ts = float(ts_str)
                        except ValueError:
                            _logger.warning(
                                "Corrupt timestamp in blocklist "
                                "entry for %s — assigning current "
                                "time so it expires after TTL",
                                fingerprint_value(
                                    domain, label="domain"
                                ),
                            )
                            cls._blocklist[domain] = now
                            legacy += 1
                            continue
                        age = now - ts
                        if age > cls._BLOCKLIST_TTL_SECONDS:
                            _logger.debug(
                                "Blocklist entry for %s expired "
                                "(age=%.1fh)",
                                fingerprint_value(
                                    domain, label="domain"
                                ),
                                age / 3600.0,
                            )
                            expired += 1
                            continue
                        cls._blocklist[domain] = ts
                        loaded += 1
                    else:
                        _logger.warning(
                            "Legacy blocklist entry for %s (no "
                            "timestamp) — assigning current time "
                            "so it expires after TTL",
                            fingerprint_value(raw, label="domain"),
                        )
                        cls._blocklist[raw] = now
                        legacy += 1
                _logger.debug(
                    "Loaded %d blocked domains from %s "
                    "(%d expired, %d legacy)",
                    loaded,
                    cls.BLOCKLIST_FILE,
                    expired,
                    legacy,
                )
            except Exception as e:
                _logger.warning(
                    "Failed to load scraper blocklist: %s", e
                )

        # Merge with settings-based blacklist (permanent).
        settings_count = 0
        if AIRUNNER_SCRAPER_BLACKLIST:
            for domain in AIRUNNER_SCRAPER_BLACKLIST:
                normalized = (
                    domain.replace("http://", "")
                    .replace("https://", "")
                    .strip("/")
                )
                if normalized not in cls._blocklist:
                    cls._blocklist[normalized] = 0.0
                    settings_count += 1

        _logger.debug(
            "Loaded %d domains from settings blacklist", settings_count
        )
        _logger.info(
            "Total blocklist size: %d domains (file + settings)",
            len(cls._blocklist),
        )
        return cls._blocklist

    @classmethod
    def get_blocklist(cls) -> Set[str]:
        """Return current set of blocked domain names (TTL-filtered)."""
        cls._load_blocklist()
        return set(cls._blocklist.keys()) if cls._blocklist else set()

    @classmethod
    def _save_blocklist(cls) -> None:
        """Persist the blocklist with timestamps.

        Settings-based entries (ts == 0.0) are omitted.
        """
        if cls._blocklist is None:
            return
        try:
            lines = []
            for domain, ts in sorted(cls._blocklist.items()):
                if ts == 0.0:
                    continue
                lines.append(f"{domain}|{ts}")
            content = "\n".join(lines) + "\n" if lines else ""
            cls.BLOCKLIST_FILE.write_text(content, encoding="utf-8")
            _logger.info(
                "Saved %d blocked domains to scraper blocklist",
                len(lines),
            )
        except Exception as e:
            _logger.warning(
                "Failed to save scraper blocklist: %s", e
            )

    # -- blocklist mutation -----------------------------------------------

    @classmethod
    def _add_to_blocklist(
        cls, url: str, reason: str = ""
    ) -> None:
        """Add *url*'s domain to the blocklist with current timestamp."""
        base_url = cls._get_base_url(url)
        blocklist = cls._load_blocklist()
        if base_url not in blocklist:
            blocklist[base_url] = time.time()
            cls._save_blocklist()
            msg = "Added blocked domain (%s)"
            if reason:
                msg += " — reason: %s"
                _logger.info(
                    msg,
                    fingerprint_value(base_url, label="domain"),
                    reason,
                )
            else:
                _logger.info(
                    msg,
                    fingerprint_value(base_url, label="domain"),
                )

    @classmethod
    def _is_blocked(cls, url: str) -> bool:
        """Return True if *url*'s domain is blocked and not expired."""
        base_url = cls._get_base_url(url)
        blocklist = cls._load_blocklist()
        if base_url not in blocklist:
            return False
        ts = blocklist[base_url]
        if ts == 0.0:  # settings-based, never expires
            return True
        age = time.time() - ts
        if age > cls._BLOCKLIST_TTL_SECONDS:
            _logger.debug(
                "Blocklist entry for %s expired (age=%.1fh) — "
                "allowing retry",
                fingerprint_value(base_url, label="domain"),
                age / 3600.0,
            )
            del blocklist[base_url]
            cls._save_blocklist()
            return False
        return True

    # -- failure tracking -------------------------------------------------

    @classmethod
    def _record_failure(cls, url: str, reason: str) -> None:
        """Record a fetch failure; blocklist after threshold reached."""
        base_url = cls._get_base_url(url)
        now = time.time()
        cls._failure_counts.setdefault(base_url, []).append(now)
        cutoff = now - cls._FAILURE_WINDOW_SECONDS
        cls._failure_counts[base_url] = [
            t for t in cls._failure_counts[base_url] if t > cutoff
        ]
        count = len(cls._failure_counts[base_url])
        _logger.warning(
            "Failure #%d for %s (%s) — threshold is %d",
            count,
            fingerprint_value(base_url, label="domain"),
            reason,
            cls._FAILURE_THRESHOLD,
        )
        if count >= cls._FAILURE_THRESHOLD:
            cls._add_to_blocklist(
                url,
                reason=(
                    f"{count} consecutive fetch failures "
                    f"(reason: {reason})"
                ),
            )

    @classmethod
    def _reset_failure_count(cls, url: str) -> None:
        """Clear failure counter for *url*'s domain."""
        base_url = cls._get_base_url(url)
        if base_url in cls._failure_counts:
            del cls._failure_counts[base_url]

    @classmethod
    def _maybe_blocklist(cls, url: str, exc: Exception) -> None:
        """Blocklist *url* only for HTTP/network errors, not import
        failures (e.g. missing trafilatura)."""
        network_errors = (
            ConnectionError,
            TimeoutError,
            socket.timeout,
            ssl.SSLError,
            OSError,
        )
        if isinstance(exc, network_errors):
            cls._add_to_blocklist(
                url, reason=f"network error: {type(exc).__name__}"
            )
            return
        exc_name = type(exc).__qualname__
        if "HTTP" in exc_name or "Connection" in exc_name:
            cls._add_to_blocklist(
                url,
                reason=f"HTTP/connection error: {exc_name}",
            )
