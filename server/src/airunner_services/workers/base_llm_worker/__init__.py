"""Shared base class for LLM generation workers (edge + cloud).

Split into a package grouped by concern; the public class
``BaseLLMWorker`` is assembled from concern-specific mixins:

- ``_state`` — in-flight conversation set and ``SignalCode`` proxy
- ``_initialization`` — constructor, abstract members, helpers
- ``_requests`` — generate / interrupt / deferred-unload handling
- ``_messages`` — queued-message dispatch and in-flight tracking
- ``_model_loading`` — model-change and RAG document loading
- ``_cleanup`` — shutdown lifecycle
"""

from __future__ import annotations

from airunner_services.llm.workers.mixins import (
    ModelDownloadMixin,
    QuantizationMixin,
    RAGIndexingMixin,
)
from airunner_services.workers.base_llm_worker._cleanup import (
    BaseLLMWorkerCleanupMixin as BaseLLMWorkerCleanupMixin,
)
from airunner_services.workers.base_llm_worker._initialization import (
    BaseLLMWorkerInitializationMixin as BaseLLMWorkerInitializationMixin,
)
from airunner_services.workers.base_llm_worker._messages import (
    BaseLLMWorkerMessageMixin as BaseLLMWorkerMessageMixin,
)
from airunner_services.workers.base_llm_worker._model_loading import (
    BaseLLMWorkerModelMixin as BaseLLMWorkerModelMixin,
)
from airunner_services.workers.base_llm_worker._requests import (
    BaseLLMWorkerRequestMixin as BaseLLMWorkerRequestMixin,
)
from airunner_services.workers.base_llm_worker._state import (
    SignalCode as SignalCode,
    _IN_FLIGHT_CONVERSATION_IDS as _IN_FLIGHT_CONVERSATION_IDS,
    _IN_FLIGHT_LOCK as _IN_FLIGHT_LOCK,
)
from airunner_services.workers.worker import Worker


class BaseLLMWorker(
    RAGIndexingMixin,
    QuantizationMixin,
    ModelDownloadMixin,
    BaseLLMWorkerRequestMixin,
    BaseLLMWorkerMessageMixin,
    BaseLLMWorkerModelMixin,
    BaseLLMWorkerCleanupMixin,
    BaseLLMWorkerInitializationMixin,
    Worker,
):
    """Shared orchestration for LLM generation (used by edge + cloud)."""


__all__ = [
    "BaseLLMWorker",
    "SignalCode",
    "_IN_FLIGHT_CONVERSATION_IDS",
    "_IN_FLIGHT_LOCK",
]
