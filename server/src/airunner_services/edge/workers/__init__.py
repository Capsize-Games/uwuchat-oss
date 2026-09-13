"""Edge Workers package — GPU-bound inference workers.

These workers run locally on edge hardware and execute model inference
through the existing signal-based pipeline. They will be moved from
``airunner_services.workers`` in a subsequent PR.

Migration checklist (Phase 6 follow-up):
    * Move ``sd_worker.py`` → edge/workers/sd_worker.py
    * Move ``tts_generator_worker.py`` → edge/workers/tts_worker.py
    * Move ``audio_processor_worker.py`` → edge/workers/audio_worker.py
    * Move ``background_removal_worker.py`` → edge/workers/rmbg_worker.py
    * Move ``safety_checker_worker.py`` → edge/workers/safety_worker.py
    * Move ``image_export_worker.py`` → edge/workers/export_worker.py
    * Move ``model_scanner_worker.py`` → edge/workers/scanner_worker.py
    * Move ``worker.py`` (base class) → shared/workers/base.py
    * Update all imports across the codebase
"""

from __future__ import annotations

__all__: list[str] = []
