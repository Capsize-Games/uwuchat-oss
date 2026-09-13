"""Contracts for runtime-backed LLM routes, one model per file."""

from airunner_services.api.routes.llm_contracts.chat_completion_request import (
    ChatCompletionRequest,
)
from airunner_services.api.routes.llm_contracts.chat_completion_response import (
    ChatCompletionResponse,
)
from airunner_services.api.routes.llm_contracts.chat_message import ChatMessage
from airunner_services.api.routes.llm_contracts.completion_request import (
    CompletionRequest,
)
from airunner_services.api.routes.llm_contracts.completion_response import (
    CompletionResponse,
)
from airunner_services.api.routes.llm_contracts.model_info import ModelInfo
from airunner_services.api.routes.llm_contracts.model_load_request import (
    ModelLoadRequest,
)
from airunner_services.api.routes.llm_contracts.rag_index_request import (
    RagIndexRequest,
)

__all__ = [
    "ChatCompletionRequest",
    "ChatCompletionResponse",
    "ChatMessage",
    "CompletionRequest",
    "CompletionResponse",
    "ModelInfo",
    "ModelLoadRequest",
    "RagIndexRequest",
]
