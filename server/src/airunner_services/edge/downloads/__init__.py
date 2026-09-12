"""Edge Downloads package — HuggingFace model download workers.

These modules handle downloading model weights from HuggingFace and
Civitai. They will be moved from ``airunner_services.downloads`` in a
subsequent PR.

Migration checklist (Phase 6 follow-up):
    * Move ``huggingface.py`` → edge/downloads/huggingface.py
    * Move ``huggingface_download_worker/`` → edge/downloads/hf_worker/
    * Keep ``policy.py`` in shared (download privacy policy is shared)
    * Update all imports across the codebase
"""

from __future__ import annotations

__all__: list[str] = []
