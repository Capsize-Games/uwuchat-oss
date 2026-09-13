"""Safety constants: length limits, injection patterns, self-harm terms."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Input length limits (enforced at the API layer)
# ---------------------------------------------------------------------------

MAX_CHATBOT_NAME_LEN: int = 50
MAX_CHATBOT_BACKGROUND_LEN: int = 1500
MAX_USER_MESSAGE_LEN: int = 2000
MAX_GENERIC_FIELD_LEN: int = 500

# ---------------------------------------------------------------------------
# Prompt injection patterns (re.IGNORECASE)
# ---------------------------------------------------------------------------

INJECTION_PATTERNS: list[str] = [
    r"ignore\s+(?:\w+\s+){0,3}(?:previous|prior|above)\s+instructions?",
    r"disregard\s+(?:\w+\s+){0,3}(?:previous|prior|above)\s+instructions?",
    r"forget\s+(?:\w+\s+){0,3}(?:previous|prior|above)\s+instructions?",
    r"you\s+are\s+(now\s+)?(actually|really|secretly)",
    r"your\s+(true|real|actual)\s+(self|name|purpose|identity)",
    r"(system|assistant|user)\s*:\s",
    r"<\s*/?s\s*>",
    r"\[INST\]",
    r"reveal\s+(your\s+)?(system\s+)?prompt",
    r"print\s+(your\s+)?(system\s+)?prompt",
    r"what\s+(are|were)\s+your\s+instructions",
    r"pretend\s+(you\s+have\s+no|there\s+are\s+no)\s+rules",
    r"do\s+anything\s+now",
    # Narrowed DAN patterns (2026-07-28, round 2) — the original
    # bare r"\bdan\b" collided with the common name "Dan" in
    # ordinary content.  Replaced with identity-assignment-anchored
    # patterns that catch jailbreak framings ("you are DAN", "act
    # as DAN") without matching standalone names ("Dan Smith").
    # The (?-i:DAN) inline flag makes only the acronym case-sensitive
    # so "you are Dan" (name) is not flagged while "you are DAN"
    # (jailbreak) still is — the outer IGNORECASE covers the verbs.
    r"\byou\s*(?:are|'re)\s+(?-i:DAN)\b",
    r"\bact\s+as\s+(?-i:DAN)\b",
    r"\bpretend\s+(?:to\s+be|you\s+(?:are|'re))\s+(?-i:DAN)\b",
    r"jailbreak",
    # P2.1 additions — common jailbreak framings not yet covered.
    r"you\s+are\s+now\s+DAN",
    r"developer\s+mode",
    r"repeat\s+the\s+words\s+above",
    r"output\s+everything\s+before\s+this\s+line",
    r"print\s+your\s+instructions\s+verbatim",
]

# ---------------------------------------------------------------------------
# Self-harm / crisis keywords (widely published by AFSP, SAVE, etc.)
# These trigger CRISIS outcome — the LLM still responds but in-character
# concern is injected and the UI shows crisis resources.
# ---------------------------------------------------------------------------

SELF_HARM_KEYWORDS: list[str] = [
    "kill myself",
    "end my life",
    "commit suicide",
    "want to die",
    "suicidal",
    "self harm",
    "self-harm",
    "cut myself",
    "hurt myself",
    "no reason to live",
    "better off dead",
    "take my own life",
]

# ---------------------------------------------------------------------------
# Topic bans for BanTopics scanner (weapon instructions / professional advice)
# ---------------------------------------------------------------------------

BAN_TOPICS: list[str] = [
    "bomb making",
    "explosive device",
    "weapon synthesis",
    "medical diagnosis",
    "legal advice",
    "financial advice",
    "how to make drugs",
]
