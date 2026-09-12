"""Tests for streamed-spacing boundary handling.

Covers two layers:

1. ``store_visible_text``'s boundary collapse — must apply only to bare
   single-DIGIT sub-word tokens (a numeric BPE continuation), never to
   single letters like "I" or "a", which are real words and must keep
   the space before the following word ("I need" must never become
   "Ineed").
2. ``_normalize_streamed_spacing`` — collapses digit-run gaps ("1 2 3"
   → "123") but must NOT insert spaces into alphanumeric identifiers
   (hex worktree IDs "71a8e2d7", commit SHAs "1ab328d25", versions
   "2.98.0", "issue #162").
"""

from __future__ import annotations

from unittest.mock import MagicMock

from airunner_services.llm.managers.mixins.node_response_generation_helper import (
    _normalize_streamed_spacing,
)
from airunner_services.llm.managers.mixins.node_streaming_response_helpers import (
    store_visible_text,
)
from airunner_services.llm.managers.mixins.node_streaming_state import (
    StreamingState,
)


def _stream(chunks: list[str]) -> list[str]:
    """Feed *chunks* through store_visible_text and return what the
    token callback received."""
    state = StreamingState()
    owner = MagicMock()
    received: list[str] = []
    owner._token_callback = received.append
    for chunk in chunks:
        store_visible_text(state, owner, request_id="req", text_to_stream=chunk)
    return received


def test_digit_run_collapses_boundary_space() -> None:
    """'1' + ' 2' + ' 3' still collapses to 123 (digit sub-words)."""
    received = _stream(["1", " 2", " 3"])
    assert "".join(received) == "123"


def test_single_letter_keeps_following_space() -> None:
    """'I' + ' need' must stay 'I need' — a letter is a real word."""
    received = _stream(["I", " need"])
    assert "".join(received) == "I need"


def test_single_letter_keeps_following_space_contraction() -> None:
    """'I' + \" can't\" must stay \"I can't\" — the regression case."""
    received = _stream(["I", " can't"])
    assert "".join(received) == "I can't"


def test_single_letter_a_keeps_following_space() -> None:
    """'a' + ' cat' must stay 'a cat'."""
    received = _stream(["a", " cat"])
    assert "".join(received) == "a cat"


def test_word_then_space_preserved() -> None:
    """A full word followed by a space-marked token keeps the space."""
    received = _stream(["hello", " world"])
    assert "".join(received) == "hello world"


def test_digit_then_space_marked_word_keeps_space() -> None:
    """'4' + ' occurrences' must stay '4 occurrences' — a digit
    followed by a real word keeps its space (regression from
    '#162directly' / '4occurrences')."""
    received = _stream(["4", " occurrences"])
    assert "".join(received) == "4 occurrences"


def test_digit_then_word_no_leading_space_untouched() -> None:
    """'1' + 'st' must stay '1st' — no leading space means no collapse."""
    received = _stream(["1", "st"])
    assert "".join(received) == "1st"


def test_no_space_no_collapse() -> None:
    """A chunk with no leading space is passed through untouched."""
    received = _stream(["I", "need"])
    assert "".join(received) == "Ineed"


# ---------------------------------------------------------------------------
# _normalize_streamed_spacing (final assembled content)
# ---------------------------------------------------------------------------


def test_normalize_collapses_digit_gaps() -> None:
    """'1 2 3' / '2 0 2 6' still collapse to contiguous digits."""
    assert _normalize_streamed_spacing("The issue number is 1 2 3") == (
        "The issue number is 123"
    )
    assert _normalize_streamed_spacing("2 0 2 6") == "2026"


def test_normalize_preserves_hex_identifier() -> None:
    """A hex worktree ID must not get spaces inserted mid-token."""
    assert _normalize_streamed_spacing("airunner-71a8e2d7") == (
        "airunner-71a8e2d7"
    )


def test_normalize_preserves_commit_sha() -> None:
    """A commit SHA (digit-leading segments) must stay intact."""
    assert _normalize_streamed_spacing("commit 1ab328d25") == (
        "commit 1ab328d25"
    )


def test_normalize_preserves_versions_and_refs() -> None:
    """Version strings and issue refs must stay intact."""
    assert _normalize_streamed_spacing("gh 2.98.0, issue #162") == (
        "gh 2.98.0, issue #162"
    )


def test_normalize_preserves_plain_words() -> None:
    """Ordinary word spacing is untouched."""
    assert _normalize_streamed_spacing("I need to check the repo") == (
        "I need to check the repo"
    )
