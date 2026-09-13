"""LLM data models.

Import all models here to ensure SQLAlchemy registers relationships properly.
"""

# Import models to register with SQLAlchemy
from airunner_services.database.models.target_files import (
    TargetFiles,
)
from airunner_services.database.models.target_directories import (
    TargetDirectories,
)
from airunner_services.database.models.chatbot import Chatbot

__all__ = ["TargetFiles", "TargetDirectories", "Chatbot"]
