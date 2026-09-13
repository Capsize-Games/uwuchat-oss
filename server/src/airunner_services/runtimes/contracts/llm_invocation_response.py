"""LLM invocation response contract."""

from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field


class LLMInvocationResponse(BaseModel):
    """Response payload for LLM invocation."""

    model_config = ConfigDict(extra="forbid")

    content: str
    tools: List[Dict[str, Any]] = Field(default_factory=list)
    usage: Dict[str, int] = Field(default_factory=dict)
