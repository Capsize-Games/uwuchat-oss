"""Shared image path-component validation.

Factored out of ``images.py`` so that the same checks are applied
consistently across HTTP and WS-RPC handlers for generated-image
endpoints.  Duplicating this logic is exactly how the WS-RPC path
skipped validation in the first place (security-audit round 6).
"""

from __future__ import annotations


def validate_date_component(date_str: str) -> str:
    """Validate that *date_str* contains exactly 8 digits (``YYYYMMDD``).

    Returns *date_str* on success; raises :class:`ValueError` with a
    human-readable message on failure so callers in both HTTP (FastAPI)
    and WS-RPC contexts can translate the error into their own response
    format.
    """
    if not date_str.isdigit() or len(date_str) != 8:
        raise ValueError("Date must be in YYYYMMDD format")
    return date_str


def validate_filename_component(filename: str) -> str:
    """Reject filenames containing path separators, null bytes, or
    directory-traversal components.

    Returns *filename* on success; raises :class:`ValueError` otherwise.
    """
    if not filename or "\x00" in filename:
        raise ValueError("Invalid filename")
    if "/" in filename or "\\" in filename:
        raise ValueError("Filename must not contain path separators")
    if filename in (".", ".."):
        raise ValueError("Invalid filename")
    return filename


__all__ = [
    "validate_date_component",
    "validate_filename_component",
]
