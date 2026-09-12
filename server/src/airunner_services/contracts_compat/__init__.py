"""Compatibility re-exports from the service runtime contracts."""

from airunner_services.runtimes.contracts import (
    ArtInvocationRequest,
    ArtInvocationResponse,
    ChatMessage,
    LLMInvocationRequest,
    LLMInvocationResponse,
    MessageRole,
    RuntimeAction,
    RuntimeDescriptor,
    RuntimeHealth,
    RuntimeHealthStatus,
    RuntimeKind,
    RuntimeMode,
    STTInvocationRequest,
    STTInvocationResponse,
    TransportKind,
)

__all__ = [
    "ArtInvocationRequest",
    "ArtInvocationResponse",
    "ChatMessage",
    "LLMInvocationRequest",
    "LLMInvocationResponse",
    "MessageRole",
    "RuntimeAction",
    "RuntimeDescriptor",
    "RuntimeHealth",
    "RuntimeHealthStatus",
    "RuntimeKind",
    "RuntimeMode",
    "STTInvocationRequest",
    "STTInvocationResponse",
    "TransportKind",
]
