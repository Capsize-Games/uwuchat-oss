"""PII masking pipeline for LLM egress.

Mask personally identifiable information before text reaches a
third-party LLM provider; restore it after the response comes back.

See ``plans/uwuchat-pii-masking-before-llm.md`` for architecture.
"""

from airunner_services.llm.pii.masker import mask_messages, mask_text
from airunner_services.llm.pii.restorer import restore_text
from airunner_services.llm.pii.vault import PIIVault

__all__ = [
    "PIIVault",
    "mask_messages",
    "mask_text",
    "restore_text",
]
