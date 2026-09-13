"""Shared module-level state for the base LLM worker.

Holds the in-flight conversation set (duplicate-generation prevention)
and the ``SignalCode`` proxy used by the worker's signal dispatch.
"""

from __future__ import annotations

import threading

from airunner_services.utils.application.enum_resolver import (
    signal_code_proxy,
)

# Set of conversation IDs with an active generation in flight.
# Guarded by ``_IN_FLIGHT_LOCK``.  Prevents duplicate (cost-doubling)
# generations when the client retries or the user sends a second
# message before the first completes.
_IN_FLIGHT_CONVERSATION_IDS: set[int] = set()
_IN_FLIGHT_LOCK = threading.Lock()

SignalCode = signal_code_proxy(
    {
        "LLM_TEXT_STREAMED_SIGNAL": "llm_text_streamed_signal",
        "LLM_TEXT_GENERATE_REQUEST_SIGNAL": (
            "llm_text_generate_request_signal"
        ),
        "LLM_CLEAR_HISTORY_SIGNAL": "llm_clear_history_signal",
        "LLM_UNLOAD_SIGNAL": "llm_unload_signal",
        "LLM_LOAD_SIGNAL": "llm_load_signal",
        "RAG_INDEX_ALL_DOCUMENTS": "rag_index_all_documents_signal",
        "RAG_INDEX_SELECTED_DOCUMENTS": (
            "rag_index_selected_documents_signal"
        ),
        "RAG_INDEXING_PROGRESS": "rag_indexing_progress_signal",
        "RAG_INDEXING_COMPLETE": "rag_indexing_complete_signal",
        "RAG_INDEX_CANCEL": "rag_index_cancel_signal",
        "RAG_LOAD_EMBEDDING": "rag_load_embedding_signal",
    },
)
