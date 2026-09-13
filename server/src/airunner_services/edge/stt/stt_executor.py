"""Re-export STTExecutor from the shared interface.

The canonical STTInferenceInterface ABC lives in
:mod:`airunner_services.shared.interfaces.stt_interface`.  This module
re-exports it as ``STTExecutor`` so existing code that imports from
``airunner_services.edge.stt.stt_executor`` continues to work.
"""

from __future__ import annotations

from airunner_services.shared.interfaces.stt_interface import (
    STTInferenceInterface as STTExecutor,
)

__all__ = ["STTExecutor"]
