"""Chat completion request."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from airunner_services.api.routes.llm_contracts.chat_message import ChatMessage


class ChatCompletionRequest(BaseModel):
    """Chat completion request."""

    messages: List[ChatMessage]
    model: Optional[str] = None
    gguf_runtime_profile: Optional[str] = None
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    stream: bool = False
    llm_overrides: Optional[Dict[str, Dict[str, Any]]] = None
    active_document_ids: Optional[List[int]] = None
