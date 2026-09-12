"""Filters for sensitive-category facts in knowledge base writes.

Facts that the memory system *infers* about a user (``source_type="inferred"``
or ``"conversation_recall"``) are checked against a keyword-based gate
before long-term storage.  If a fact appears to concern a GDPR Article 9
special category — religion, political opinion, health, sexual orientation,
race/ethnic origin, trade union membership, or genetic/biometric data — it
is silently dropped rather than persisted.

Facts the user *directly and explicitly tells* their own companion
(``source_type="user_stated"``) are **not** filtered — that is the core,
explicitly-consented-to product behavior.

This is a heuristic/keyword-based first-pass filter that errs toward
over-blocking (preferring false positives — dropping a non-sensitive
fact — over false negatives that would retain sensitive data). It is
documented as a reasonable-effort safeguard, not a perfect filter.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# ── GDPR Article 9 sensitive-category keyword patterns ────────────────
# When a fact matches one of these regexes, it is assumed to concern a
# sensitive category and is dropped.  Patterns are case-insensitive.
# Organised as (category_label, compiled_regex) tuples so the log message
# can describe *which* category triggered the filter.

_SENSITIVE_PATTERNS: list[tuple[str, re.Pattern]] = [
    # Religion / philosophical belief
    (
        "religion",
        re.compile(
            r"(?i)\b(religion|religious|muslim|christian|catholic|"
            r"protestant|jewish|judaism|hindu|buddhist|sikh|jain|"
            r"atheist|atheism|agnostic|pagan|spiritual\s+belief|"
            r"faith\b|churchgoer|mosque|temple\s+attendance|"
            r"converted\s+to|born.again|evangelical|orthodox\s+jew|"
            r"sunni|shia|baptist|methodist|lutheran|mormon|"
            r"shinto|taoist|confucian|zoroastrian|baha)"
        ),
    ),
    # Political opinion
    (
        "politics",
        re.compile(
            r"(?i)\b(political|politician|party\s+(affiliation|member)|"
            r"republican|democrat|conservative|liberal|socialist|"
            r"communist|anarchist|libertarian|fascist|nazi|"
            r"voted\s+for|campaign\s+donat|political\s+view|"
            r"left.wing|right.wing|centrist|progressive|"
            r"populist|authoritarian|extremist|"
            r"electoral|ballot|voting\s+(record|preference))"
        ),
    ),
    # Health (physical or mental)
    (
        "health",
        re.compile(
            r"(?i)\b(health\s+(condition|issue|problem|diagnosis)|"
            r"illness|disease|diagnos\w+\s+with|cancer|tumor|"
            r"diabetes|heart\s+(disease|condition)|stroke|"
            r"chronic\s+(pain|illness|condition)|autoimmune|"
            r"mental\s+(health|illness|disorder)|depression|"
            r"anxiety\s+disorder|bipolar|schizophrenia|ptsd|"
            r"ocd|adhd|autism|alzheimer|dementia|"
            r"hospitalized|surgery|medical\s+(condition|history)|"
            r"prescription|medication|therapy\s+for|"
            r"disabled|disability|handicap|"
            r"hiv|aids|hepatitis|covid|long.covid|"
            r"allergic\s+to|allergy|chemotherapy|"
            r"insulin|blood\s+pressure\s+(medication|issues?)|"
            r"asthma|epilepsy|migraine)"
        ),
    ),
    # Sexual orientation
    (
        "orientation",
        re.compile(
            r"(?i)\b(sexual\s+orientation|gay|lesbian|bisexual|"
            r"pansexual|asexual|homosexual|heterosexual|"
            r"queer\b|sexuality|closeted|out\s+as\b|"
            r"straight\b|lgb|lgbt|transgender|trans\b|non.binary|"
            r"gender\s+identity|cisgender|cisfemale|cismale|"
            r"same.sex|coming\s+out)"
        ),
    ),
    # Race or ethnic origin
    (
        "race",
        re.compile(
            r"(?i)\b(race\b|racial|ethnic\s+(origin|background|group)|"
            r"caucasian|white\b|black\b|african.american|asian\b|"
            r"hispanic|latino|latina|latinx|native.american|"
            r"indigenous\s+(people|population|tribe)|"
            r"mixed.race|biracial|multiracial|"
            r"discriminat\w+\s+(against|based\s+on)|"
            r"colour\s+of\s+(their|my|his|her)\s+skin|"
            r"minority\b|person.of.colour)"
        ),
    ),
    # Trade union membership
    (
        "union",
        re.compile(
            r"(?i)\b(trade\s+union|union\s+member|labor\s+union|"
            r"unionized|unionisation|collective\s+bargaining|"
            r"strike\s+action|union\s+representative|"
            r"union\s+(dues|membership|participation))"
        ),
    ),
    # Genetic / biometric data
    (
        "biometric",
        re.compile(
            r"(?i)\b(dna\b|genetic\s+(test|data|information|"
            r"predisposition|marker|condition|disorder)|"
            r"genome|gene\s+therapy|hereditary|inherited\s+"
            r"(condition|disease|disorder)|"
            r"biometric\s+(data|scan|identifier|authentication)|"
            r"fingerprint|retina\s+scan|facial\s+recognition|"
            r"23andme|ancestry\s+dna|genetic\s+testing)"
        ),
    ),
]


def _is_sensitive_fact(fact: str) -> tuple[bool, str]:
    """Check *fact* against sensitive-category keyword patterns.

    Returns ``(True, category)`` if the fact matches a sensitive category,
    or ``(False, "")`` if it passes the gate.
    """
    for category, pattern in _SENSITIVE_PATTERNS:
        if pattern.search(fact):
            return True, category
    return False, ""


def filter_inferred_fact(
    fact: str,
    source_type: str,
) -> tuple[bool, str]:
    """Filter one inferred fact before knowledge base persistence.

    Args:
        fact: The fact text to check.
        source_type: One of ``"user_stated"``, ``"inferred"``,
            ``"web_search"``, ``"conversation_recall"``.

    Returns:
        A ``(blocked, category)`` tuple.  When *blocked* is ``True``, the
        fact should not be persisted.  *category* describes which
        sensitive category matched (for logging).

    Facts with ``source_type="user_stated"`` are never blocked — the user
    directly telling their own companion something is the core,
    explicitly-consented-to product behavior, not passive inference by the
    system.
    """
    if source_type == "user_stated":
        return False, ""

    if source_type in ("inferred", "conversation_recall"):
        is_sensitive, category = _is_sensitive_fact(fact)
        if is_sensitive:
            logger.info(
                "Blocked inferred sensitive fact [%s] (len=%d)",
                category,
                len(fact),
            )
            return True, category

    return False, ""
