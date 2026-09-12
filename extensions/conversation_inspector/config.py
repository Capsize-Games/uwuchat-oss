"""Extension configuration for the Conversation Flow Inspector."""

from airunner_services.extensions.config import ExtensionConfig


class ConversationInspectorExtension(ExtensionConfig):
    name = "conversation_inspector"
    label = "Conversation Flow Inspector"
    description = (
        "Superuser tool to visualize full AI agent conversation flows "
        "including system prompts, RAG documents, tool calls, thinking, "
        "and LangGraph node traversal."
    )
