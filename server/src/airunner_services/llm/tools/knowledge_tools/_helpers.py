"""
Shared helpers for knowledge tools.

Contains deduplication and merge logic used by recall_knowledge
to combine results from multiple search backends.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


def merge_search_results(
    rag_results: list[str],
    keyword_results: list[dict[str, str]],
    tfidf_results: list[dict[str, str]],
) -> list[str]:
    """Merge and deduplicate search results from multiple sources.

    Results are sorted most-recent-first (DESC by timestamp).  RAG
    results carry no timestamp so they sort last.  Duplicates (by
    normalized line content) are skipped.

    Args:
        rag_results: Results from RAG/semantic search.
        keyword_results: Results from keyword search
            (each a dict with "line" and optional "timestamp" keys).
        tfidf_results: Results from TF-IDF search
            (each a dict with "line" and optional "timestamp" keys).

    Returns:
        Deduplicated list of result strings, most recent first.

    """
    seen: set[str] = set()
    # Collect (line, sort_key) — RAG results have no timestamp so
    # they use an empty string which sorts last in descending.
    entries: list[tuple[str, str]] = []

    def _add(line: str, ts: str = "") -> None:
        clean = line.strip().lstrip("- ")
        if clean not in seen:
            entries.append((clean, ts))
            seen.add(clean)

    for r in rag_results:
        _add(r)
    for r in keyword_results:
        _add(r.get("line", ""), r.get("timestamp", ""))
    for r in tfidf_results:
        _add(r.get("line", ""), r.get("timestamp", ""))

    # Sort descending by timestamp — empty strings sort last
    entries.sort(key=lambda e: e[1], reverse=True)
    # Format: "[YYYY-MM-DD HH:MM:SS] fact text" when timestamp
    # is present, otherwise just the fact text.
    formatted: list[str] = []
    for line, ts in entries:
        if ts:
            formatted.append(f"[{ts}] {line}")
        else:
            formatted.append(line)
    return formatted
