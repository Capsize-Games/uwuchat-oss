"""Newspaper system — REST API routes.

Mount at ``/api/v1/newspaper``.  Endpoints proxy requests to the
FastSearch newspaper API and add LLM-quality summarization.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()


# ------------------------------------------------------------------
# Request / Response schemas
# ------------------------------------------------------------------


class NewspaperResponse(BaseModel):
    """Response for ``GET /``."""

    newspaper: str = ""
    cached: bool = False
    cache_age_seconds: int = 0
    error: Optional[str] = None


class SummarizeRequest(BaseModel):
    """Request body for ``POST /summarize``."""

    url: Optional[str] = None
    text: Optional[str] = None


class SummarizeResponse(BaseModel):
    """Response for ``POST /summarize``."""

    summary: str = ""
    url: Optional[str] = None
    error: Optional[str] = None


class RefreshResponse(BaseModel):
    """Response for ``POST /refresh``."""

    success: bool
    message: str
    newspaper_length: int = 0


class StatusResponse(BaseModel):
    """Response for ``GET /status``."""

    cache_available: bool
    snapshot: Optional[str] = None
    cache_age_seconds: int = 0


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.get("/", response_model=NewspaperResponse)
async def get_newspaper(
    location: str = Query(
        default="",
        description="Location for weather (e.g. 'Denver, CO')",
    ),
    interests: str = Query(
        default="",
        description="Comma-separated interest tags",
    ),
    force_refresh: bool = Query(
        default=False,
        description="Skip cache and re-fetch from FastSearch",
    ),
    format: str = Query(
        default="json",
        description="Response format: 'json' or 'markdown'",
    ),
) -> Dict[str, Any]:
    """Return today's newspaper from FastSearch (cached locally).

    Args:
        location: Optional location string for weather.
        interests: Optional comma-separated interest tags.
        force_refresh: If true, bypass the local cache.
        format: ``"json"`` (wraps in JSON envelope) or ``"markdown"``
            (returns raw text/markdown).

    Returns:
        JSON envelope with newspaper markdown and cache metadata.
    """
    try:
        from extensions.fastsearch.server.provider import (
            FastSearchProvider,
        )
        from projects.uwuchat.server.newspaper.proxy import (
            NewspaperProxy,
        )

        provider = FastSearchProvider()
        proxy = NewspaperProxy(provider)
        loc = location if location else None
        ints = interests if interests else None
        markdown = await proxy.get_newspaper(
            location=loc,
            interests=ints,
            force_refresh=force_refresh,
        )
        return {
            "newspaper": markdown,
            "cached": True,
            "cache_age_seconds": 0,
        }
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch newspaper: {exc}",
        )


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.post("/summarize", response_model=SummarizeResponse)
async def summarize(body: SummarizeRequest) -> Dict[str, Any]:
    """Generate an LLM-quality summary of a URL or text.

    Args:
        body: JSON with ``url`` and/or ``text`` fields.

    Returns:
        Summary string with optional URL echo.
    """
    if not body.url and not body.text:
        raise HTTPException(
            status_code=400,
            detail="Provide either 'url' or 'text' to summarise.",
        )
    try:
        from projects.uwuchat.server.newspaper.summarizer import (
            ArticleSummarizer,
        )

        summarizer = ArticleSummarizer()
        if body.url:
            summary = await summarizer.summarize_url(body.url)
            return {"summary": summary, "url": body.url}
        summary = await summarizer.summarize_text(body.text or "")
        return {"summary": summary}
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Summarization failed: {exc}",
        )


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.post("/refresh", response_model=RefreshResponse)
async def refresh(
    location: str = Query(
        default="",
        description="Location for weather (e.g. 'Denver, CO')",
    ),
) -> Dict[str, Any]:
    """Force-refresh the newspaper cache.

    Args:
        location: Optional location string.

    Returns:
        Success status and newspaper length.
    """
    try:
        from extensions.fastsearch.server.provider import (
            FastSearchProvider,
        )
        from projects.uwuchat.server.newspaper.proxy import (
            NewspaperProxy,
        )

        provider = FastSearchProvider()
        proxy = NewspaperProxy(provider)
        loc = location if location else None
        markdown = await proxy.get_newspaper(
            location=loc,
            force_refresh=True,
        )
        return {
            "success": True,
            "message": "Newspaper cache refreshed.",
            "newspaper_length": len(markdown),
        }
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Refresh failed: {exc}",
        )


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.get("/status", response_model=StatusResponse)
async def status() -> Dict[str, Any]:
    """Return the current cache status and compact snapshot.

    Returns:
        Cache availability, age, and snapshot preview.
    """
    try:
        from projects.uwuchat.server.newspaper.proxy import (
            get_newspaper_proxy,
        )

        proxy = get_newspaper_proxy()
        snapshot = proxy.get_compact_snapshot()
        return {
            "cache_available": snapshot is not None,
            "snapshot": snapshot,
            "cache_age_seconds": 0,
        }
    except RuntimeError:
        return {
            "cache_available": False,
            "snapshot": None,
            "cache_age_seconds": 0,
        }
