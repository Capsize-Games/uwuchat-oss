"""Deterministic claim-matching against grounding sources.

No model dependency — pure text matching using token overlap and
fuzzy substring matching (difflib).
"""

from __future__ import annotations

import difflib
import re
from typing import Tuple

# Claims shorter than this (in characters) are never matched
# against sources — single-word or very short claims produce
# too many false positives.
_MIN_CLAIM_CHARS = 12

# SequenceMatcher ratio threshold for fuzzy substring matching.
# Claims with a match above this ratio are considered "supported."
_FUZZY_THRESHOLD = 0.6

# Token-overlap ratio threshold.  At least this fraction of the
# claim's significant words must appear in a source for it to
# count as token-supported.
# Speed heuristic: sources with at least this token overlap get
# fuzzy-matched (expensive).  Sources below this are skipped.
_TOKEN_OVERLAP_THRESHOLD = 0.4

# Independent pass threshold: when a claim has at least this
# fraction of its significant words appearing in a source, it
# is considered supported even when the fuzzy ratio is below
# _FUZZY_THRESHOLD.  Set from audit data (0.65 captures
# grounded paraphrases with character-level similarity as low
# as 0.41 while rejecting claims that change key facts).
_TOKEN_PASS_THRESHOLD = 0.7


def check_claims_against_sources(
    claims: list[str],
    sources: list[str],
) -> list[dict]:
    """Return per-claim support verdicts against the given sources.

    Each result dict contains:
        claim       — the original claim string
        supported   — bool, True if the claim is backed by >=1 source
        best_score  — highest fuzzy-match ratio (0.0–1.0)
        best_snippet— relevant source excerpt (max 200 chars)
    """
    results: list[dict] = []
    for claim in claims:
        clean = claim.strip()
        if not clean:
            results.append(
                {
                    "claim": claim,
                    "supported": True,
                    "best_score": 1.0,
                    "best_snippet": "(empty claim)",
                }
            )
            continue
        if len(clean) < _MIN_CLAIM_CHARS:
            results.append(
                {
                    "claim": claim,
                    "supported": True,
                    "best_score": 1.0,
                    "best_snippet": (
                        "(claim too short for grounding check)"
                    ),
                }
            )
            continue

        supported, score, snippet = _match_claim(clean, sources)
        results.append(
            {
                "claim": claim,
                "supported": supported,
                "best_score": score,
                "best_snippet": snippet,
            }
        )
    return results


# ------------------------------------------------------------------


def _match_claim(
    claim: str, sources: list[str]
) -> Tuple[bool, float, str]:
    """Check one claim against all sources; return (supported, score,
    snippet)."""
    if not sources:
        return False, 0.0, "(no grounding sources available this turn)"

    claim_lower = claim.lower()
    significant = _significant_words(claim_lower)
    if not significant:
        return False, 0.0, "(claim has no matchable words)"

    best_score = 0.0
    best_token = 0.0
    best_snippet = ""
    for src in sources:
        src_lower = src.lower()
        # Compute token overlap first — cheap.
        overlap_ratio = _token_overlap_ratio(significant, src_lower)
        if overlap_ratio > best_token:
            best_token = overlap_ratio
            # Only extract a snippet when this is the best token match
            # so far — keep the fuzzy-derived snippet as primary when
            # token overlap didn't improve.
            if overlap_ratio >= _TOKEN_PASS_THRESHOLD and (
                best_score < _FUZZY_THRESHOLD
            ):
                best_snippet = _extract_snippet(src, claim_lower)
        if overlap_ratio >= _TOKEN_OVERLAP_THRESHOLD:
            # Confirm with fuzzy matching for a precise score
            fuzzy = _best_fuzzy_ratio(claim_lower, src_lower)
            if fuzzy > best_score:
                best_score = fuzzy
                best_snippet = _extract_snippet(src, claim_lower)
            if fuzzy >= _FUZZY_THRESHOLD:
                return True, fuzzy, best_snippet
            continue
        # Slow path: fuzzy match even without token overlap
        fuzzy = _best_fuzzy_ratio(claim_lower, src_lower)
        if fuzzy > best_score:
            best_score = fuzzy
            best_snippet = _extract_snippet(src, claim_lower)
        if fuzzy >= _FUZZY_THRESHOLD:
            return True, fuzzy, best_snippet

    supported = (
        best_score >= _FUZZY_THRESHOLD
        or best_token >= _TOKEN_PASS_THRESHOLD
    )
    return supported, best_score, best_snippet


# ------------------------------------------------------------------
# Token / word extraction
# ------------------------------------------------------------------

_WORD_RE = re.compile(r"\b[a-z0-9]{4,}\b")


def _significant_words(text: str) -> set[str]:
    """Return lowercase words with >=4 characters."""
    return set(_WORD_RE.findall(text))


def _token_overlap_ratio(claim_words: set[str], source: str) -> float:
    """Fraction of claim words present in source."""
    src_words = _WORD_RE.findall(source)
    if not claim_words:
        return 0.0
    hits = sum(1 for w in claim_words if w in src_words)
    return hits / len(claim_words)


# ------------------------------------------------------------------
# Fuzzy matching
# ------------------------------------------------------------------


def _best_fuzzy_ratio(needle: str, haystack: str) -> float:
    """Return the best SequenceMatcher ratio sliding needle across
    haystack.

    For haystacks longer than 2× the needle, slides a window
    of needle length across the haystack to find the best local
    match.
    """
    if len(needle) > len(haystack):
        return difflib.SequenceMatcher(
            None, needle, haystack
        ).ratio()
    if len(haystack) <= len(needle) * 2:
        return difflib.SequenceMatcher(
            None, needle, haystack
        ).ratio()
    best = 0.0
    step = max(1, len(needle) // 2)
    for start in range(0, len(haystack) - len(needle) + 1, step):
        window = haystack[start : start + len(needle) * 2]
        ratio = difflib.SequenceMatcher(None, needle, window).ratio()
        if ratio > best:
            best = ratio
    return best


# ------------------------------------------------------------------
# Snippet extraction
# ------------------------------------------------------------------


def _extract_snippet(source: str, claim_lower: str, context: int = 200) -> str:
    """Return a relevant excerpt from *source* around the best fuzzy
    match to *claim_lower*."""
    if len(source) <= context:
        return source

    # Find the most significant word from the claim (>= 5 chars)
    # and locate it in the source for an anchor point.
    anchor_pos = _find_anchor(source, claim_lower)
    if anchor_pos >= 0:
        half = context // 2
        begin = max(0, anchor_pos - half)
        end = min(len(source), begin + context)
        snippet = source[begin:end]
        if begin > 0:
            snippet = "…" + snippet
        if end < len(source):
            snippet = snippet + "…"
        return snippet

    # Fallback: sliding window for claims with no common tokens.
    best_start = 0
    best_score = 0.0
    step = max(1, len(claim_lower) // 2)
    half = context // 2
    for start in range(0, max(1, len(source) - context), step):
        window = source[start : start + context]
        ratio = difflib.SequenceMatcher(
            None, claim_lower, window.lower()
        ).ratio()
        if ratio > best_score:
            best_score = ratio
            best_start = start
    begin = max(0, best_start - half)
    end = min(len(source), begin + context)
    snippet = source[begin:end]
    if begin > 0:
        snippet = "…" + snippet
    if end < len(source):
        snippet = snippet + "…"
    return snippet


def _find_anchor(source: str, claim_lower: str) -> int:
    """Find the position in *source* of the longest significant word
    from *claim_lower*, or -1 if none found."""
    words = sorted(
        _significant_words(claim_lower), key=len, reverse=True
    )
    src_lower = source.lower()
    for word in words:
        if len(word) < 5:
            continue
        pos = src_lower.find(word)
        if pos >= 0:
            return pos
    return -1
