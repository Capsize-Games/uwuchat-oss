"""LLM message role enum."""

from enum import Enum


class MessageRole(str, Enum):
    """LLM message roles shared by API and runtime requests."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
