"""Non-LLM email preprocessing — stripping, classification (Phase 2).

Runs before any LLM call — entirely algorithmic, no model cost.
Contact extraction now lives in ``contacts.py``.
"""

from __future__ import annotations

import re
from typing import Any

# Common patterns for signature and quote stripping.
_SIG_DELIMITER = re.compile(r"^--\s*$", re.MULTILINE)
_QUOTE_PATTERN = re.compile(
    r"^On\s+.+wrote:\s*$", re.MULTILINE | re.IGNORECASE,
)
_QUOTE_LINE = re.compile(r"^>\s?", re.MULTILINE)

# Automated email detection heuristics. Kept to unambiguous
# transactional senders — a broader match (e.g. "alerts", "billing")
# risks misclassifying mail the user actually wants read, like a
# bank alert or a freelance invoice; those are caught by subject
# text instead, where the context is clearer.
_AUTOMATED_FROM = re.compile(
    r"(no-?reply|noreply|donotreply|bounce"
    r"|auto-confirm|order-?update|shipment-?tracking|receipts?@)",
    re.IGNORECASE,
)
_AUTOMATED_DOMAINS = frozenset({
    "mailchimp", "sendgrid", "klaviyo", "convertkit",
    "constantcontact", "mailgun", "postmark", "hubspot",
    "marketo", "activecampaign", "drip",
})
_AUTOMATED_SUBJECTS = (
    "unsubscribe", "newsletter",
    "order confirmation", "your order", "order #",
    "has shipped", "shipping confirmation", "out for delivery",
    "delivered", "tracking number", "your receipt",
    "payment confirmation", "invoice #", "your invoice",
    "statement is ready", "auto-generated", "do not reply",
)


def strip_quoted_content(body: str) -> str:
    """Remove quoted reply blocks and signature lines.

    Uses the common ``On ... wrote:`` pattern, leading ``>`` quote
    markers, and the ``-- `` signature delimiter.  Returns cleaned
    plaintext.
    """
    text = body or ""
    # Truncate at first "On ... wrote:" pattern.
    match = _QUOTE_PATTERN.search(text)
    if match:
        text = text[:match.start()].strip()
    # Strip leading > quote markers from remaining lines.
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        if _QUOTE_LINE.match(line) and not line.strip().startswith(">"):
            continue
        cleaned.append(line)
    text = "\n".join(cleaned)
    # Truncate at signature delimiter.
    match = _SIG_DELIMITER.search(text)
    if match:
        text = text[:match.start()].strip()
    return text.strip()


def classify_automated(msg: Any) -> bool:
    """Return True if an email is likely automated/transactional —
    receipts, shipping notices, newsletters — and not worth
    summarizing. *msg* is a provider-level EmailMessage (dataclass
    from ``.provider``), not an ORM model.
    """
    from_addr = (getattr(msg, "from_address", "") or "").lower()
    if _AUTOMATED_FROM.search(from_addr):
        return True
    for domain in _AUTOMATED_DOMAINS:
        if domain in from_addr:
            return True
    subject_lower = (getattr(msg, "subject", "") or "").lower()
    return any(h in subject_lower for h in _AUTOMATED_SUBJECTS)
