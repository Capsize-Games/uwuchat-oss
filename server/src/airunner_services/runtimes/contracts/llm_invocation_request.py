"""LLM invocation request contract."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from airunner_services.runtimes.contracts.chat_message import ChatMessage


class LLMInvocationRequest(BaseModel):
    """Request payload for LLM invocation."""

    model_config = ConfigDict(extra="forbid")

    model: Optional[str] = None
    messages: List[ChatMessage] = Field(default_factory=list)
    max_tokens: Optional[int] = None
    temperature: float = 0.7
    stream: bool = False
    tool_choice: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
