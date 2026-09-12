"""
Illegal content keyword list — base64-encoded.

Keywords are NOT committed to this repository. Populate ``_ENCODED``
manually on each deployment. See the wiki for encoding instructions:
  airunner.wiki/UwuChat-Safety-Architecture.md § 8

DO NOT decode or print these values in logs or error messages.

To encode a keyword:
    import base64
    base64.b64encode("keyword".encode()).decode()

To verify an entry:
    import base64
    base64.b64decode("dGVzdA==").decode()

On production, consider injecting via a secrets manager rather than
committing encoded values here.
"""

from __future__ import annotations

import base64
from typing import List

_ENCODED: List[str] = [
    # Add base64-encoded keyword strings here, one per line.
    # Example format (not a real keyword): "dGVzdA==",
]

ILLEGAL_KEYWORDS: List[str] = [
    base64.b64decode(e).decode() for e in _ENCODED
]
