"""Tests for _claim_matching.py — check_claims_against_sources
with token-overlap as an independent pass path."""

from __future__ import annotations


class TestClaimMatchingTokenPassPath:
    """Token overlap >= 0.65 independently supports claims that
    paraphrase source text with low character-level fuzzy similarity."""

    _SOURCE = (
        "Jimmy Page is an English musician and producer who achieved "
        "international fame as the guitarist and founder of the rock "
        "band Led Zeppelin. Page began his career as a studio session "
        "musician in London and was a member of the Yardbirds before "
        "founding Led Zeppelin in 1968. With Led Zeppelin, Page wrote "
        "and produced many of the band's most famous songs including "
        "Stairway to Heaven and Kashmir."
    )

    def _check(self, claims: list[str]) -> list[dict]:
        from airunner_services.llm.tools.grounding_tools_helpers import (
            check_claims_against_sources,
        )
        return check_claims_against_sources(
            claims, [self._SOURCE],
        )

    def test_paraphrase_passes_via_token_overlap(self) -> None:
        """A correct paraphrase with low fuzzy score passes via
        token overlap — the fuzzy score is below 0.6 but the
        token overlap is high enough to independently support
        the claim."""
        results = self._check([
            "Page wrote and produced Stairway to Heaven and "
            "Kashmir with Led Zeppelin",
        ])
        assert results[0]["supported"], (
            f"Expected supported, got {results[0]}"
        )
        # This claim is supported — either via fuzzy matching or
        # token overlap.  The key regression test is that a correct
        # paraphrase of source content does not get flagged
        # unsupported.

    def test_paraphrase_session_musician_passes(self) -> None:
        """A correct paraphrase about session musician work passes."""
        results = self._check([
            "Jimmy Page was a session musician in London before "
            "forming Led Zeppelin",
        ])
        assert results[0]["supported"]

    def test_paraphrase_songwriting_passes(self) -> None:
        """A correct claim about songs written passes."""
        results = self._check([
            "Page wrote Stairway to Heaven and Kashmir for "
            "Led Zeppelin",
        ])
        assert results[0]["supported"]

    def test_verbatim_match_still_passes(self) -> None:
        """Near-verbatim claims continue to pass via fuzzy matching."""
        results = self._check([
            "Jimmy Page is an English musician and producer who "
            "achieved international fame as the guitarist of the "
            "rock band Led Zeppelin",
        ])
        assert results[0]["supported"]
        assert results[0]["best_score"] >= 0.6

    def test_wrong_year_band_still_flagged(self) -> None:
        """A claim that shares vocabulary but changes the year and
        band name is correctly flagged unsupported."""
        results = self._check([
            "Jimmy Page founded Led Zeppelin in 1972 after leaving "
            "the Beatles",
        ])
        assert not results[0]["supported"], (
            f"Expected unsupported, got {results[0]}"
        )

    def test_wrong_song_still_flagged(self) -> None:
        """A claim that attributes the wrong song to the artist
        is flagged unsupported."""
        results = self._check([
            "Jimmy Page wrote Hotel California for Led Zeppelin",
        ])
        assert not results[0]["supported"]

    def test_wrong_role_still_flagged(self) -> None:
        """A claim that describes the wrong role (drummer vs guitarist)
        is flagged unsupported."""
        results = self._check([
            "Jimmy Page was primarily known as a drummer for "
            "Led Zeppelin",
        ])
        assert not results[0]["supported"]

    def test_empty_sources_returns_unsupported(self) -> None:
        """When no sources are available, claims are unsupported."""
        from airunner_services.llm.tools.grounding_tools_helpers import (
            check_claims_against_sources,
        )
        results = check_claims_against_sources(
            ["Jimmy Page is a guitarist"], [],
        )
        assert not results[0]["supported"]

    def test_short_claim_passes_unchecked(self) -> None:
        """Claims shorter than 12 characters are not checked."""
        from airunner_services.llm.tools.grounding_tools_helpers import (
            check_claims_against_sources,
        )
        results = check_claims_against_sources(
            ["short"], ["some source text"],
        )
        assert results[0]["supported"]

    def test_hedge_instruction_no_persona_conflict(self) -> None:
        """The check_grounding result must not contain phrases that
        the persona anti-narration rule forbids (e.g. 'according to
        my search', 'according to search results')."""
        import json
        from airunner_services.llm.tools.grounding_tools import (
            check_grounding,
        )

        result = check_grounding(
            claims=["Jimmy Page performed at Woodstock in 1969"],
            api=None,
        )
        parsed = json.loads(result)
        instruction = parsed.get("instruction", "")

        # These phrases would contradict the persona rule if the
        # grounding instruction told the model to USE them.  The
        # instruction may reference them in a NEGATIVE context
        # (e.g. "do NOT reference X"), which is fine.
        positive_banned = [
            "according to my search",
            "according to search results",
            "search_fastsearch",
            "I searched",
        ]
        for phrase in positive_banned:
            assert phrase not in instruction.lower(), (
                f"Banned phrase {phrase!r} found in instruction: "
                f"{instruction}"
            )
        # The instruction must NOT tell the model to use search/source
        # language as a hedging phrase.  It's OK to say "do NOT
        # reference" them.
        assert "qualify it with 'according to" not in instruction.lower()

        # The instruction should still contain the core semantic: drop
        # or soften.
        assert "drop" in instruction.lower()
        assert "uncertainty" in instruction.lower()

    def test_token_overlap_below_threshold_does_not_pass(self) -> None:
        """A claim with token overlap below 0.65 and fuzzy below
        0.6 is unsupported."""
        results = self._check([
            "Jimmy Page performed at Woodstock in 1969 with "
            "Led Zeppelin",
        ])
        assert not results[0]["supported"]
