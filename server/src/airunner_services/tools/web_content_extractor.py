import multiprocessing
import hashlib
import json
import os
from typing import Optional, List, Dict
from pathlib import Path

try:
    from sumy.parsers.plaintext import PlaintextParser
    from sumy.nlp.tokenizers import Tokenizer
    from sumy.summarizers.lsa import LsaSummarizer
except ImportError:
    PlaintextParser = None  # type: ignore[assignment]
    Tokenizer = None  # type: ignore[assignment]
    LsaSummarizer = None  # type: ignore[assignment]
from airunner_services.settings import (
    AIRUNNER_BASE_PATH,
    AIRUNNER_LOG_LEVEL,
)
from airunner_services.database.models.path_settings import PathSettings
from airunner_services.tools.scraper_blocklist import ScraperBlocklistMixin
from airunner_services.url_safety import (
    SSRFBlocked,
    validate_url_for_fetch,
)
from airunner_services.utils.application import get_logger
from airunner_services.utils.application.log_hygiene import fingerprint_value


# Patch signals for subprocesses
def _patch_signals_for_subprocess():
    if multiprocessing.current_process().name != "MainProcess":
        try:
            import twisted.internet._signals

            twisted.internet._signals.install = lambda *a, **kw: None
            if hasattr(twisted.internet._signals, "SignalReactorMixin"):
                twisted.internet._signals.SignalReactorMixin.install = (
                    lambda *a, **kw: None
                )
        except Exception:
            pass
        try:
            import scrapy.utils.ossignal

            scrapy.utils.ossignal.install_shutdown_handlers = (
                lambda *a, **kw: None
            )
        except Exception:
            pass


_patch_signals_for_subprocess()


# Dynamically resolve cache directory based on PathSettings
def _get_base_path() -> Path:
    """Get the base path for cache and blocklist persistence."""
    return Path(AIRUNNER_BASE_PATH)


try:
    path_settings = PathSettings.objects.first()
    if path_settings and path_settings.base_path:
        base_path = Path(path_settings.base_path)
    else:
        # Use the shared base path as fallback.
        base_path = _get_base_path()
    CACHE_DIR = base_path / "cache" / ".webcache"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    BLOCKLIST_FILE = base_path / ".scraper_blocklist"
except Exception:
    # Fall back to the shared base path when settings are unavailable.
    base_path = _get_base_path()
    CACHE_DIR = base_path / "cache" / ".webcache"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    BLOCKLIST_FILE = base_path / ".scraper_blocklist"

logger = get_logger(__name__, AIRUNNER_LOG_LEVEL)

__all__ = ["WebContentExtractor"]


class WebContentExtractor(ScraperBlocklistMixin):
    """Fetches, extracts, cleans, summarizes, and caches main content
    from web pages, delegating fetch+extraction to the FastSearch
    /api/scrape/ endpoint.
    """

    CACHE_DIR = CACHE_DIR
    CACHE_EXPIRY_DAYS = None  # No expiry for now
    BLOCKLIST_FILE = BLOCKLIST_FILE

    # ------------------------------------------------------------------
    # FastSearch HTTP helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _call_fastsearch_scrape(url: str) -> Optional[Dict]:
        """Call the FastSearch /api/scrape/ endpoint for *url*.

        Returns the JSON response dict on success, or None on any
        failure (network error, non-200, missing config, etc.).
        """
        import requests as _requests

        base_url = os.environ.get("FASTSEARCH_BASE_URL", "").rstrip("/")
        api_key = os.environ.get("FASTSEARCH_API_KEY", "")
        if not base_url:
            logger.warning("FASTSEARCH_BASE_URL not configured")
            return None
        headers = {"X-API-Key": api_key} if api_key else {}
        try:
            resp = _requests.get(
                f"{base_url}/api/scrape/",
                params={"url": url},
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning(
                "FastSearch scrape failed for %s: %s",
                fingerprint_value(url, label="url"),
                exc,
            )
            return None

    @staticmethod
    def _classify_fastsearch_error(
        error_msg: str,
    ) -> Optional[Exception]:
        """Convert a FastSearch error string to an exception type.

        Returns an Exception suitable for ``_maybe_blocklist`` when
        the error indicates a target-site network failure (connection
        refused, timeout).  Returns ``None`` for errors that do not
        indicate the target site is dead (API key, config, etc.).
        """
        msg_lower = error_msg.lower()
        if "timed out" in msg_lower:
            return TimeoutError(error_msg)
        if (
            "could not connect" in msg_lower
            or "connection" in msg_lower
        ):
            return ConnectionError(error_msg)
        return None

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _url_to_cache_path(url: str) -> Path:
        h = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return WebContentExtractor.CACHE_DIR / f"{h}.txt"

    @staticmethod
    def _url_to_metadata_cache_path(url: str) -> Path:
        """Get cache path for metadata (JSON) version of URL."""
        h = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return WebContentExtractor.CACHE_DIR / f"{h}_meta.json"

    @staticmethod
    def get_cached(url: str) -> Optional[str]:
        path = WebContentExtractor._url_to_cache_path(url)
        if path.exists():
            try:
                return path.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning(
                    "Failed to read cache for %s: %s",
                    fingerprint_value(url, label="url"),
                    e,
                )
        return None

    @staticmethod
    def get_cached_metadata(url: str) -> Optional[Dict]:
        """Get cached metadata for a URL if available."""
        path = WebContentExtractor._url_to_metadata_cache_path(url)
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(
                    "Failed to read metadata cache for %s: %s",
                    fingerprint_value(url, label="url"),
                    e,
                )
        return None

    @staticmethod
    def set_cache(url: str, text: str):
        path = WebContentExtractor._url_to_cache_path(url)
        try:
            path.write_text(text, encoding="utf-8")
        except Exception as e:
            logger.warning(
                "Failed to write cache for %s: %s",
                fingerprint_value(url, label="url"),
                e,
            )

    @staticmethod
    def set_metadata_cache(url: str, metadata: Dict):
        """Cache metadata for a URL."""
        path = WebContentExtractor._url_to_metadata_cache_path(url)
        try:
            path.write_text(
                json.dumps(metadata, indent=2), encoding="utf-8"
            )
        except Exception as e:
            logger.warning(
                "Failed to write metadata cache for %s: %s",
                fingerprint_value(url, label="url"),
                e,
            )

    # ------------------------------------------------------------------
    # Public fetch + extract methods
    # ------------------------------------------------------------------

    @staticmethod
    def fetch_and_extract(
        url: str, use_cache: bool = True
    ) -> Optional[str]:
        """Fetch, extract, and summarize main content as plaintext
        from a URL, using cache if available."""
        try:
            validate_url_for_fetch(url)
        except SSRFBlocked as e:
            logger.warning(
                "Blocked URL (%s): %s",
                fingerprint_value(url, label="url"),
                e,
            )
            return None

        if WebContentExtractor._is_blocked(url):
            logger.info(
                "Skipping blocked domain: %s",
                WebContentExtractor._get_base_url(url),
            )
            return None

        cached = WebContentExtractor.get_cached(url)
        if use_cache and cached:
            return cached

        data = WebContentExtractor._call_fastsearch_scrape(url)
        if data and data.get("content"):
            summarized_text = WebContentExtractor._summarize_text(
                data["content"]
            )
            WebContentExtractor.set_cache(url, summarized_text)
            WebContentExtractor._reset_failure_count(url)
            return summarized_text

        # Fast-blocklist target-site network errors reported by
        # FastSearch (connection refused, timeout from the target).
        if data and "error" in data:
            exc = WebContentExtractor._classify_fastsearch_error(
                data["error"]
            )
            if exc is not None:
                WebContentExtractor._maybe_blocklist(url, exc)

        WebContentExtractor._record_failure(
            url, "fetch_and_extract failed"
        )
        return None

    @staticmethod
    def fetch_and_extract_with_metadata_raw(
        url: str, use_cache: bool = True, summarize: bool = False
    ) -> Optional[Dict]:
        """Fetch and extract main content with metadata from a URL.

        Delegates fetching and HTML extraction to FastSearch
        /api/scrape/.  SSRF validation, blocklisting, and caching
        remain in airunner.

        Args:
            url: The URL to fetch and extract.
            use_cache: Whether to use cache.
            summarize: Whether to apply Sumy summarization
                (default: False for raw content).

        Returns:
            Dictionary with:
            - content: Clean text content (raw or summarized)
            - title: Page title (from FastSearch)
            - description: None (FastSearch endpoint does not
              currently return metadata)
            - author: None (same)
            - publish_date: None (same)
            Returns None if extraction fails.
        """
        try:
            validate_url_for_fetch(url)
        except SSRFBlocked as e:
            logger.warning(
                "Blocked URL (%s): %s",
                fingerprint_value(url, label="url"),
                e,
            )
            return None

        if WebContentExtractor._is_blocked(url):
            logger.info(
                "Skipping blocked domain (%s)",
                fingerprint_value(
                    WebContentExtractor._get_base_url(url),
                    label="domain",
                ),
            )
            return None

        if use_cache:
            cached_metadata = WebContentExtractor.get_cached_metadata(url)
            if cached_metadata:
                if summarize and "content" in cached_metadata:
                    logger.debug(
                        "Using cached summarized metadata for %s",
                        fingerprint_value(url, label="url"),
                    )
                    return cached_metadata
                elif not summarize and "raw_content" in cached_metadata:
                    logger.debug(
                        "Using cached raw metadata for %s",
                        fingerprint_value(url, label="url"),
                    )
                    result = cached_metadata.copy()
                    result["content"] = result.pop("raw_content")
                    return result

        data = WebContentExtractor._call_fastsearch_scrape(url)
        if not data or "error" in data:
            reason = (
                data.get("error", "no response")
                if data
                else "fetch returned no content"
            )
            logger.warning(
                "Failed to fetch content from %s: %s",
                fingerprint_value(url, label="url"),
                reason,
            )
            # Fast-blocklist target-site network errors reported by
            # FastSearch (connection refused, timeout from the
            # target).
            if data and "error" in data:
                exc = (
                    WebContentExtractor
                    ._classify_fastsearch_error(data["error"])
                )
                if exc is not None:
                    WebContentExtractor._maybe_blocklist(url, exc)
            WebContentExtractor._record_failure(url, reason)
            return None

        main_text = data.get("content", "")
        if not main_text:
            logger.warning(
                "No main text extracted from %s",
                fingerprint_value(url, label="url"),
            )
            return None

        summarized_text = WebContentExtractor._summarize_text(main_text)
        content_text = summarized_text if summarize else main_text

        result = {
            "content": content_text,
            "title": data.get("title"),
            "description": data.get("description"),
            "author": data.get("author"),
            "publish_date": data.get("publish_date"),
        }

        if use_cache:
            cache_entry = result.copy()
            cache_entry["raw_content"] = main_text
            cache_entry["content"] = summarized_text
            WebContentExtractor.set_metadata_cache(url, cache_entry)
            logger.debug(
                "Cached raw and summarized content for %s",
                fingerprint_value(url, label="url"),
            )

        WebContentExtractor._reset_failure_count(url)
        return result

    @staticmethod
    def fetch_and_extract_with_metadata(
        url: str, use_cache: bool = True
    ) -> Optional[Dict]:
        """Fetch, extract, and summarize main content with metadata.

        Args:
            url: The URL to fetch and extract.
            use_cache: Whether to use cache.

        Returns:
            Dictionary with content, title, description, author,
            publish_date.  Returns None if extraction fails.
        """
        return WebContentExtractor.fetch_and_extract_with_metadata_raw(
            url, use_cache=use_cache, summarize=True
        )

    @staticmethod
    def extract_with_links(
        url: str, content: Optional[str] = None
    ) -> Optional[Dict]:
        """Extract content, links, and metadata from a URL or HTML.

        Args:
            url: The URL being processed (for absolute URL
                resolution).
            content: Optional HTML content.  If not provided,
                delegates to FastSearch for fetching.

        Returns:
            Dictionary with content, links (list of dicts), and
            metadata (dict with title, description, author,
            publish_date).  Returns None if extraction fails.
        """
        try:
            if content is None:
                data = WebContentExtractor._call_fastsearch_scrape(url)
                if not data or "error" in data:
                    logger.warning(
                        "Failed to fetch content from %s",
                        fingerprint_value(url, label="url"),
                    )
                    return None
                main_text = data.get("content", "")
                metadata_dict = {
                    "title": data.get("title"),
                    "description": data.get("description"),
                    "author": data.get("author"),
                    "publish_date": data.get("publish_date"),
                    "url": url,
                }
                links = []
            else:
                # Extract main text from HTML using BeautifulSoup
                from bs4 import BeautifulSoup

                soup = BeautifulSoup(content, "html.parser")
                # Remove script, style, nav, footer, header
                for tag in soup(
                    ["script", "style", "nav", "footer", "header"]
                ):
                    tag.decompose()
                main_text = soup.get_text("\n", strip=True)

                if not main_text:
                    logger.warning(
                        "No main text extracted from %s",
                        fingerprint_value(url, label="url"),
                    )
                    return None

                # Extract metadata from HTML meta tags
                metadata_dict = (
                    WebContentExtractor._extract_html_metadata(
                        content, url
                    )
                )

                # Extract links from HTML
                links = WebContentExtractor._extract_links_from_html(
                    url, content, main_text
                )

            return {
                "content": main_text,
                "links": links,
                "metadata": metadata_dict,
            }

        except Exception as e:
            logger.error(
                "extract_with_links failed for %s: %s",
                fingerprint_value(url, label="url"),
                e,
                exc_info=True,
            )
            return None

    # ------------------------------------------------------------------
    # HTML metadata extraction (BeautifulSoup – replaces trafilatura)
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_html_metadata(
        html_content: str, url: str
    ) -> Dict:
        """Extract metadata from HTML meta tags.

        Args:
            html_content: Raw HTML string.
            url: The source URL (used as fallback title).

        Returns:
            Dict with title, description, author, publish_date, url.
        """
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html_content, "html.parser")

        # Title
        title = None
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)

        # Description (meta name="description" or og:description)
        description = None
        for meta in soup.find_all("meta"):
            name = (meta.get("name") or "").lower()
            prop = (meta.get("property") or "").lower()
            content_attr = meta.get("content", "").strip()
            if not content_attr:
                continue
            if name == "description" or prop == "og:description":
                description = content_attr
                break

        # Author (meta name="author" or article:author)
        author = None
        for meta in soup.find_all("meta"):
            name = (meta.get("name") or "").lower()
            content_attr = meta.get("content", "").strip()
            if not content_attr:
                continue
            if name in ("author", "article:author"):
                author = content_attr
                break

        # Publish date (article:published_time, etc.)
        publish_date = None
        for meta in soup.find_all("meta"):
            prop = (meta.get("property") or "").lower()
            name = (meta.get("name") or "").lower()
            content_attr = meta.get("content", "").strip()
            if not content_attr:
                continue
            if prop == "article:published_time" or name in (
                "published_time",
                "date",
            ):
                publish_date = content_attr
                break

        return {
            "title": title,
            "description": description,
            "author": author,
            "publish_date": publish_date,
            "url": url,
        }

    # ------------------------------------------------------------------
    # Link extraction (unchanged from original)
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_links_from_html(
        base_url: str, html_content: str, main_text: str
    ) -> List[Dict]:
        """Extract links with anchor text and context from HTML."""
        try:
            from bs4 import BeautifulSoup
            from urllib.parse import urljoin, urlparse

            soup = BeautifulSoup(html_content, "html.parser")
            links = []
            seen_urls = set()

            main_content_area = (
                soup.find("article")
                or soup.find("main")
                or soup.body
                or soup
            )

            for link_tag in main_content_area.find_all("a", href=True):
                href = link_tag.get("href", "").strip()

                if (
                    not href
                    or href.startswith("#")
                    or href.startswith("javascript:")
                ):
                    continue

                absolute_url = urljoin(base_url, href)

                parsed = urlparse(absolute_url)
                if parsed.scheme not in ("http", "https"):
                    continue

                if absolute_url in seen_urls:
                    continue
                seen_urls.add(absolute_url)

                anchor_text = link_tag.get_text(strip=True)
                if not anchor_text:
                    continue

                context = WebContentExtractor._get_link_context(
                    link_tag, anchor_text
                )

                if WebContentExtractor._is_likely_navigation_link(
                    anchor_text, context
                ):
                    continue

                links.append(
                    {
                        "url": absolute_url,
                        "anchor_text": anchor_text,
                        "context": context,
                    }
                )

            logger.info("Extracted %d links from page", len(links))
            return links

        except Exception as e:
            logger.error(
                "Link extraction failed: %s", e, exc_info=True
            )
            return []

    @staticmethod
    def _get_link_context(
        link_tag, anchor_text: str, max_context_chars: int = 200
    ) -> str:
        """Get surrounding text context for a link."""
        try:
            parent_p = link_tag.find_parent(
                ["p", "div", "li", "td"]
            )
            if parent_p:
                context_text = parent_p.get_text(
                    separator=" ", strip=True
                )

                if len(context_text) > max_context_chars:
                    anchor_pos = context_text.find(anchor_text)
                    if anchor_pos != -1:
                        start = max(
                            0, anchor_pos - max_context_chars // 2
                        )
                        end = min(
                            len(context_text),
                            anchor_pos
                            + len(anchor_text)
                            + max_context_chars // 2,
                        )
                        context_text = context_text[start:end]
                        if start > 0:
                            context_text = "..." + context_text
                        if end < len(context_text):
                            context_text = context_text + "..."

                return context_text

            return anchor_text

        except Exception:
            return anchor_text

    @staticmethod
    def _is_likely_navigation_link(
        anchor_text: str, context: str
    ) -> bool:
        """Heuristic to filter out navigation/footer links."""
        nav_patterns = [
            "home",
            "about",
            "contact",
            "privacy",
            "terms",
            "sitemap",
            "login",
            "register",
            "sign in",
            "sign up",
            "logout",
            "menu",
            "search",
            "subscribe",
            "follow us",
            "share",
            "previous",
            "next",
            "back to",
            "return to",
            "copyright",
            "all rights reserved",
        ]

        anchor_lower = anchor_text.lower()

        if len(anchor_text) < 3:
            return True

        for pattern in nav_patterns:
            if pattern in anchor_lower:
                return True

        if (
            anchor_text.replace(" ", "")
            .replace("-", "")
            .replace("\u00bb", "")
            .replace("\u00ab", "")
            .isdigit()
        ):
            return True

        return False

    # ------------------------------------------------------------------
    # Summarization (unchanged – still uses sumy in-process)
    # ------------------------------------------------------------------

    @staticmethod
    def _summarize_text(
        text: str, max_sentences: int = 15
    ) -> str:
        """Summarize the extracted text using Sumy.

        Args:
            text: Text to summarize.
            max_sentences: Maximum number of sentences
                (default 15 for research purposes).

        Returns:
            Summarized text, or original if summarization fails.
        """
        try:
            parser = PlaintextParser.from_string(
                text, Tokenizer("english")
            )
            summarizer = LsaSummarizer()
            summary = summarizer(parser.document, max_sentences)
            return "\n\n".join(
                str(sentence) for sentence in summary
            )
        except Exception as e:
            logger.error("Sumy summarization failed: %s", e)
            return (
                text[:5000] if len(text) > 5000 else text
            )
