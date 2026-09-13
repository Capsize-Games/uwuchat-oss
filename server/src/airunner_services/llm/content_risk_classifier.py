"""Content risk classifier for user messages.

Pure heuristics, no ML model, no network.  Returns a float 0.0–1.0
where 0.0 = completely innocuous and 1.0 = high-risk content requiring
full safety treatment.  Conservative by design — false negatives are
more costly than false positives.
"""

from __future__ import annotations

import re
from typing import Tuple

# ── Injection patterns (imported from memory_updater) ──────────────────────

_INJECTION_PATTERNS = [
    re.compile(
        r"(?i)(ignore|forget|disregard).{0,30}"
        r"(previous|above|prior|instructions?|directives?)"
    ),
    re.compile(
        r"(?i)(your|new|actual|real|true).{0,20}"
        r"(directive|instruction|purpose|goal|task|role)"
    ),
    re.compile(
        r"(?i)(from now on|henceforth|starting now).{0,40}"
        r"(you (are|should|must|will))"
    ),
    re.compile(
        r"(?i)(you are (now|actually|really)|pretend (you are|to be))"
    ),
    re.compile(r"(?i)<\s*(system|instructions?|prompt)\b"),
]

# ── Risk signal constants ───────────────────────────────────────────────────

_SELF_HARM_TERMS: frozenset[str] = frozenset(
    {
        "kill myself",
        "suicide",
        "self harm",
        "end it all",
        "don't want to live",
        "hurt myself",
        "cut myself",
        "overdose",
        "want to die",
        "take my own life",
        "no reason to live",
        "better off dead",
        "self-harm",
        "selfharm",
    }
)

_MINOR_AGE_TERMS: frozenset[str] = frozenset(
    {
        "years old",
        "teenager",
        "child",
        "minor",
        "underage",
        "age ",
        "little girl",
        "little boy",
        "young girl",
        "young boy",
        "kid",
        "schoolgirl",
        "schoolboy",
        "toddler",
        "preschool",
    }
)

_SEXUAL_TERMS: frozenset[str] = frozenset(
    {
        "sexual",
        "sex",
        "porn",
        "nude",
        "naked",
        "erotic",
        "fetish",
        "incest",
        "rape",
        "molest",
        "groom",
        "nsfw",
        "xxx",
        "adult content",
    }
)

_WEAPON_DRUG_TERMS: frozenset[str] = frozenset(
    {
        "how to make",
        "synthesize",
        "build a bomb",
        "instructions for",
        "recipe for",
        "manufacture",
    }
)

_WEAPON_NOUNS: frozenset[str] = frozenset(
    {
        "bomb",
        "explosive",
        "detonator",
        "gunpowder",
        "ammunition",
        "napalm",
        "mustard gas",
        "sarin",
        "ricin",
        "anthrax",
        "c4",
        "semtex",
        "pipe bomb",
        "ied",
        "molotov",
        "methamphetamine",
        "meth",
        "fentanyl",
        "heroin",
        "cocaine",
        "lsd",
        "ecstasy",
        "mdma",
    }
)

_PROFESSIONAL_ADVICE_URGENT: frozenset[str] = frozenset(
    {
        "diagnose me",
        "is this legal",
        "should i invest",
        "my symptoms",
        "what medication",
        "medical advice",
        "legal advice",
        "tax advice",
        "sue",
        "lawsuit",
        "file for",
    }
)

_WEIGHT_SELF_HARM: float = 0.35
_WEIGHT_MINOR_SEXUAL: float = 0.30
_WEIGHT_SYNTHESIS: float = 0.20
_WEIGHT_PROFESSIONAL: float = 0.10
_WEIGHT_INJECTION: float = 0.05


# ── Public API ──────────────────────────────────────────────────────────────


def score(text: str) -> float:
    """Return risk score in [0.0, 1.0].  Never raises."""
    try:
        if not text or not text.strip():
            return 0.0
        lower = text.lower()
        return _clamp(
            _WEIGHT_SELF_HARM * _self_harm_signal(lower)
            + _WEIGHT_MINOR_SEXUAL * _minor_sexual_signal(lower)
            + _WEIGHT_SYNTHESIS * _synthesis_signal(lower)
            + _WEIGHT_PROFESSIONAL * _professional_advice_signal(lower)
            + _WEIGHT_INJECTION * _injection_signal(text)
        )
    except Exception:
        return 0.0


def risk_tier(score_val: float) -> str:
    """Map score to tier name: innocuous | low | moderate | high."""
    if score_val < 0.05:
        return "innocuous"
    if score_val < 0.25:
        return "low"
    if score_val < 0.60:
        return "moderate"
    return "high"


def classify(text: str) -> Tuple[float, str]:
    """Return (score, tier_name).  Never raises."""
    s = score(text)
    return s, risk_tier(s)


# ── Signal functions ────────────────────────────────────────────────────────


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp *value* to [*lo*, *hi*]."""
    return max(lo, min(hi, value))


def _self_harm_signal(lower: str) -> float:
    """Check for self-harm / suicide keywords."""
    hits = sum(1 for term in _SELF_HARM_TERMS if term in lower)
    return min(hits / 2.0, 1.0)


def _minor_sexual_signal(lower: str) -> float:
    """Check for sexual content combined with age indicators."""
    has_sexual = any(term in lower for term in _SEXUAL_TERMS)
    if not has_sexual:
        return 0.0
    has_age = any(term in lower for term in _MINOR_AGE_TERMS)
    if has_age:
        return 1.0
    return 0.1


def _synthesis_signal(lower: str) -> float:
    """Check for weapons/drug synthesis requests."""
    has_synthesis = any(term in lower for term in _WEAPON_DRUG_TERMS)
    has_weapon = any(term in lower for term in _WEAPON_NOUNS)
    if has_synthesis and has_weapon:
        return 1.0
    if has_weapon and (
        "how" in lower or "make" in lower or "create" in lower
    ):
        return 0.7
    if has_synthesis:
        return 0.4
    return 0.0


def _professional_advice_signal(lower: str) -> float:
    """Check for professional advice requests with urgency."""
    hits = sum(1 for term in _PROFESSIONAL_ADVICE_URGENT if term in lower)
    if hits >= 2:
        return 1.0
    if hits == 1:
        return 0.5
    if "diagnose" in lower or "prescribe" in lower:
        return 0.4
    return 0.0


def _injection_signal(text: str) -> float:
    """Apply prompt injection patterns and return hit ratio."""
    hits = sum(1 for p in _INJECTION_PATTERNS if p.search(text))
    return min(hits / 3.0, 1.0)


__all__ = ["score", "risk_tier", "classify"]
