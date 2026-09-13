"""Service-owned LLM generation worker.

Split into a package grouped by concern; the public class
``LLMGenerateWorker`` is assembled from concern-specific mixins:

- ``_state`` — ``SignalCode`` proxy
- ``_initialization`` — constructor, provider flags, conversation handlers
- ``_model_manager`` — shared model-manager lazy configuration
- ``_requests`` — generate / interrupt / deferred-unload handling
- ``_messages`` — queued-message dispatch and result finalization
- ``_model_loading`` — model load / unload and threaded tenant loading
- ``_rag`` — RAG document loading
- ``_inactivity`` — idle auto-unload timer
- ``_cleanup`` — shutdown lifecycle
"""

from __future__ import annotations

from airunner_services.edge.workers.llm_generate_worker._cleanup import (
    LLMGenerateWorkerCleanupMixin,
)
from airunner_services.edge.workers.llm_generate_worker._inactivity import (
    LLMGenerateWorkerInactivityMixin,
)
from airunner_services.edge.workers.llm_generate_worker._initialization import (
    LLMGenerateWorkerInitializationMixin,
)
from airunner_services.edge.workers.llm_generate_worker._messages import (
    LLMGenerateWorkerMessageMixin,
)
from airunner_services.edge.workers.llm_generate_worker._model_loading import (
    LLMGenerateWorkerModelLoadingMixin,
)
from airunner_services.edge.workers.llm_generate_worker._model_manager import (
    LLMGenerateWorkerModelManagerMixin,
)
from airunner_services.edge.workers.llm_generate_worker._rag import (
    LLMGenerateWorkerRagMixin,
)
from airunner_services.edge.workers.llm_generate_worker._requests import (
    LLMGenerateWorkerRequestMixin,
)
from airunner_services.edge.workers.llm_generate_worker._state import (
    SignalCode as SignalCode,
)
from airunner_services.llm.workers.mixins import (
    ModelDownloadMixin,
    QuantizationMixin,
    RAGIndexingMixin,
)
from airunner_services.workers.worker import Worker


class LLMGenerateWorker(
    RAGIndexingMixin,
    QuantizationMixin,
    ModelDownloadMixin,
    LLMGenerateWorkerRequestMixin,
    LLMGenerateWorkerMessageMixin,
    LLMGenerateWorkerModelLoadingMixin,
    LLMGenerateWorkerRagMixin,
    LLMGenerateWorkerInactivityMixin,
    LLMGenerateWorkerCleanupMixin,
    LLMGenerateWorkerModelManagerMixin,
    LLMGenerateWorkerInitializationMixin,
    Worker,
):
    """Orchestrate LLM requests, model loading, and retry behavior."""


__all__ = [
    "LLMGenerateWorker",
    "SignalCode",
]
