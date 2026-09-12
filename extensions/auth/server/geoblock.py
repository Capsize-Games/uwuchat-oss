"""EU/UK geoblocking — IP-based region check for registration and login.

Uses the free `ip-api.com <http://ip-api.com/json/>`_ lookup (no API key
required; 45 requests/minute rate limit).  Results are cached in memory
for the duration of the process to stay within the rate limit.

The blocked country list is read from the ``AIRUNNER_BLOCKED_COUNTRY_CODES``
environment variable as a comma-separated list of ISO 3166-1 alpha-2 codes.
When unset, no blocking is applied.

IP-based geolocation is inherently imperfect (VPNs, proxies). This is an
accepted limitation — no VPN detection is attempted.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from urllib.request import Request, urlopen

from fastapi import Request as FastAPIRequest

logger = logging.getLogger(__name__)

# ── EU/EEA member states (ISO 3166-1 alpha-2) ──────────────────────────
# Includes the 27 EU member states plus the 3 EEA-but-non-EU states
# (Norway, Iceland, Liechtenstein) which are bound by materially the
# same GDPR-equivalent regime via the EEA agreement.
_EU_EEA_CODES: frozenset[str] = frozenset({
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR",
    "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL",
    "PL", "PT", "RO", "SK", "SI", "ES", "SE",  # EU-27 (without UK)
    "NO", "IS", "LI",  # EEA non-EU
})

_UK_CODE: frozenset[str] = frozenset({"GB"})

# Non-EU/EEA jurisdictions with a GDPR-equivalent "special category /
# sensitive personal data" regime — default-prohibited processing
# absent consent, not just a general consent requirement:
#   CH — Switzerland: revised FADP (2023), closely mirrors GDPR
#        including a near-identical sensitive-data category. Not EU/EEA,
#        so it needs its own entry.
#   KR — South Korea: PIPA, widely regarded as at least as strict as
#        GDPR, with rigorous explicit-consent requirements.
#   BR — Brazil: LGPD, explicitly modeled on GDPR with a near-identical
#        sensitive personal data list.
#   CN — China: PIPL, strict sensitive-personal-information category
#        plus data-localization/cross-border-transfer rules that add
#        complexity beyond consent alone.
#
# Deliberately NOT included: Japan (APPI), India (DPDP Act), Canada
# (PIPEDA) — all consent-based regimes without a GDPR-style default
# prohibition, handled instead via an explicit consent flow at
# registration rather than a hard block. See the sensitive-data
# consent plan for that mechanism.
_OTHER_STRICT_CODES: frozenset[str] = frozenset({
    "CH", "KR", "BR", "CN",
})

# Headers checked for the real client IP when behind a reverse proxy.
# Ordered by decreasing trust — the outermost proxy's header is last.
_FORWARDED_HEADERS = ("x-forwarded-for", "x-real-ip")

# Trusted proxy CIDRs.  X-Forwarded-For / X-Real-IP headers are only
# honoured when the immediate peer (request.client.host) is within one
# of these ranges.  Add your reverse proxy's Docker network CIDR here.
_TRUSTED_PROXY_CIDRS: tuple[str, ...] = tuple(
    c.strip()
    for c in os.environ.get(
        "AIRUNNER_TRUSTED_PROXY_CIDRS",
        "172.16.0.0/12,10.0.0.0/8",
    ).split(",")
    if c.strip()
)


def blocked_country_codes() -> frozenset[str]:
    """Return the configured blocked ISO country codes.

    Reads from the ``AIRUNNER_BLOCKED_COUNTRY_CODES`` env var. When unset,
    defaults to EU/EEA member states, the UK, and other jurisdictions with
    a GDPR-equivalent special-category-data regime (Switzerland, South
    Korea, Brazil, Japan, China). When set, the value is used as-is
    (comma-separated ISO codes).

    This is config-driven so the region list can be adjusted without a
    code change — EU accession, UK status changes, etc.
    """
    raw = (os.environ.get("AIRUNNER_BLOCKED_COUNTRY_CODES") or "").strip()
    if raw:
        return frozenset(c.strip().upper() for c in raw.split(",") if c.strip())
    # Default: EU-27 + EEA + UK + other GDPR-equivalent jurisdictions
    return _EU_EEA_CODES | _UK_CODE | _OTHER_STRICT_CODES


def _is_trusted_proxy(ip: str) -> bool:
    """Return ``True`` if *ip* is within a trusted proxy CIDR range."""
    import ipaddress

    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for cidr_str in _TRUSTED_PROXY_CIDRS:
        try:
            network = ipaddress.ip_network(cidr_str, strict=False)
        except ValueError:
            continue
        if addr in network:
            return True
    return False


def _extract_client_ip(request: FastAPIRequest) -> str | None:
    """Extract the real client IP from the request.

    ``X-Forwarded-For`` and ``X-Real-IP`` headers are only honoured
    when the immediate peer (``request.client.host``) is a known
    trusted proxy.  Otherwise the headers are ignored — any client
    can spoof them — and ``request.client.host`` is used directly.

    Only the first address in ``X-Forwarded-For`` is used, matching
    the standard proxy behaviour of prepending the real client IP.
    """
    peer_host = (
        request.client.host if request.client is not None else None
    )
    peer_is_trusted = (
        _is_trusted_proxy(peer_host) if peer_host else False
    )

    if peer_is_trusted:
        for header in _FORWARDED_HEADERS:
            value = request.headers.get(header, "").strip()
            if value:
                # X-Forwarded-For may be a comma-separated chain;
                # the real client IP is the first address.
                first = value.split(",")[0].strip()
                if first:
                    return first

    return peer_host


async def resolve_country(request: FastAPIRequest) -> str | None:
    """Return the ISO country code for the client IP, or ``None``.

    Returns ``None`` for private/reserved IPs, missing client IPs,
    and failed lookups — callers treat ``None`` as "unknown region."

    This is the **single country-resolution entry point** for the
    codebase.  Both ``check_geoblock`` and the sensitive-data consent
    check call this function so there is exactly one IP→country
    resolution path.
    """
    client_ip = _extract_client_ip(request)
    if not client_ip:
        return None

    if _is_private_ip(client_ip):
        return None

    country = await asyncio.to_thread(_lookup_country, client_ip)
    if country is None:
        logger.warning(
            "Geoblock lookup failed for %s — allowing access", client_ip
        )
        return None

    return country


async def check_geoblock(request: FastAPIRequest) -> str | None:
    """Return a user-facing message if the client is in a blocked region,
    or ``None`` if access is allowed.

    When the IP is a private/reserved address, access is allowed (no
    geoblocking for loopback, LAN, or unknown clients).
    """
    country = await resolve_country(request)
    if country is None:
        return None

    blocked = blocked_country_codes()
    if country in blocked:
        logger.info(
            "Geoblock rejected access from %s", country
        )
        return (
            "UwUchat is not available in your region. "
            "This is a deliberate product decision — we are not "
            "currently accepting users from the European Union, "
            "European Economic Area, or the United Kingdom. "
            "We apologize for the inconvenience."
        )

    return None


def _is_private_ip(ip: str) -> bool:
    """Return True for private/reserved IP addresses (IPv4 and IPv6).

    Covers all RFC 1918 / RFC 6598 / RFC 3927 / RFC 4291 ranges:
    - 10.0.0.0/8, 127.0.0.0/8, 169.254.0.0/16, 172.16.0.0/12,
      192.168.0.0/16 (IPv4)
    - ::1, fc00::/7, fe80::/10 (IPv6 loopback, unique-local,
      link-local)
    """
    import ipaddress

    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False

    if addr.is_loopback:
        return True
    if addr.is_private:
        return True
    if addr.is_link_local:
        return True
    # Also cover reserved ranges that is_private doesn't catch.
    if isinstance(addr, ipaddress.IPv4Address):
        # 169.254.0.0/16 — link-local for IPv4
        if addr.is_link_local:
            return True
    return False


# ── In-memory cache ───────────────────────────────────────────────────
_cache: dict[str, tuple[str, float]] = {}  # ip -> (country, expiry)
_CACHE_TTL = 300  # 5 minutes


def _lookup_country(ip: str) -> str | None:
    """Return the ISO country code for *ip*, or None on failure.

    Uses the free ip-api.com endpoint with a simple in-memory cache.
    This function is synchronous/blocking — callers should offload it
    to a thread via ``asyncio.to_thread``.

    *ip* ultimately comes from the client-supplied ``X-Forwarded-For``
    header (the first hop in the chain is always client-controlled,
    by design of that header) — it is validated as a well-formed IP
    address here, before being embedded in the request URL, rather
    than trusting it as an opaque string.
    """
    import ipaddress

    try:
        ipaddress.ip_address(ip)
    except ValueError:
        logger.debug("Rejecting malformed IP for geolocation: %r", ip)
        return None

    now = time.time()
    cached = _cache.get(ip)
    if cached is not None and cached[1] > now:
        return cached[0]

    try:
        url = f"http://ip-api.com/json/{ip}?fields=countryCode"
        req = Request(url, headers={"User-Agent": "UwUchat/1.0"})
        # Scheme is a fixed "http://ip-api.com/..." literal (never
        # variable) and ip is now validated above, so this isn't a
        # scheme-confusion / arbitrary-URL open.
        resp = urlopen(req, timeout=5)  # nosec B310
        data = json.loads(resp.read().decode())
        country = data.get("countryCode", "") or ""
        if country:
            _cache[ip] = (country, now + _CACHE_TTL)
        return country or None
    except Exception as exc:
        logger.debug("IP geolocation failed for %s: %s", ip, exc)
        return None
