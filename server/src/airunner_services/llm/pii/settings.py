"""PII masking feature flag — env-driven, default off.

The framework default is ``False`` (opt-in).  The UwUchat project
overlay flips it to ``True`` via
``projects/uwuchat/server/conf/settings.py``.
"""

import os


def _read_flag() -> bool:
    """Read ``AIRUNNER_PII_MASKING_ENABLED`` from the environment."""
    value = os.environ.get("AIRUNNER_PII_MASKING_ENABLED", "0")
    return value.strip().lower() in {"1", "true", "yes", "on"}


PII_MASKING_ENABLED = _read_flag()

# Re-export the name the plan expects so both import styles work.
AIRUNNER_PII_MASKING_ENABLED = PII_MASKING_ENABLED
