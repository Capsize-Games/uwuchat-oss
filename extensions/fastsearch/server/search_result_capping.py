"""Aggregate size caps for multi-query FastSearch tool results.

Keeps whole per-query blocks and drops trailing queries when the
running character total would exceed the configured ceiling.
"""

from __future__ import annotations

import os

# Maximum aggregate characters across all query blocks in a single
# ``search_fastsearch`` or ``search_fastsearch_news`` call.
# Default 8 000 chars (~2 000 tokens), consistent with the topic-
# brief cap.  Separate env var so deployments can tune search-
# result budgets independently of topic-brief budgets.
_SEARCH_RESULTS_MAX_CHARS = int(
    os.getenv("FASTSEARCH_SEARCH_RESULTS_MAX_CHARS", "8000")
)


def _format_dropped_note(dropped_queries: list[str]) -> str:
    """Return a markdown note naming which queries were dropped."""
    count = len(dropped_queries)
    label = "y" if count == 1 else "ies"
    names = ", ".join(
        f"'{q[:60]}'" for q in dropped_queries[:5]
    )
    if count > 5:
        names += f", and {count - 5} more"
    return (
        "\n\n---\n"
        "*[Search results truncated: {count} quer{label} "
        "dropped for size — {names}. "
        "Re-query individually if needed.]*"
    ).format(count=count, label=label, names=names)


def _collect_blocks(
    formatted_parts: list[str],
    per_query_results: list[dict],
    max_chars: int,
) -> tuple[list[str], list[int], list[str]]:
    """Walk blocks; return (kept_parts, kept_indices, dropped_names)."""
    kept: list[str] = []
    kept_idx: list[int] = []
    running = 0
    dropped: list[str] = []

    for i, part in enumerate(formatted_parts):
        sep = len("\n\n") if kept else 0
        if running + sep + len(part) <= max_chars:
            kept.append(part)
            kept_idx.append(i)
            running += sep + len(part)
        else:
            result = (
                per_query_results[i]
                if i < len(per_query_results)
                else {}
            )
            dropped.append(
                result.get("query", f"query {i+1}")
            )

    return kept, kept_idx, dropped


def cap_query_blocks(
    formatted_parts: list[str],
    per_query_results: list[dict],
    max_chars: int | None = None,
) -> tuple[list[str], list[dict]]:
    """Cap *formatted_parts* at *max_chars* by dropping trailing queries.

    Whole per-query blocks are kept or dropped — never cut mid-block.
    A single query block is always emitted even if it alone exceeds
    the cap.  Appends a truncation note naming dropped queries.
    """
    if max_chars is None:
        max_chars = _SEARCH_RESULTS_MAX_CHARS
    if len(formatted_parts) <= 1:
        return formatted_parts, per_query_results

    kept, kept_idx, dropped = _collect_blocks(
        formatted_parts, per_query_results, max_chars
    )
    if dropped:
        kept.append(_format_dropped_note(dropped))
        return kept, [per_query_results[i] for i in kept_idx]

    return kept, per_query_results
