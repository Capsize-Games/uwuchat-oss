"""Service-owned database model compatibility surface."""

from airunner_services.database.models.active_grid_settings import (
    ActiveGridSettings,
)
from airunner_services.database.models.agent_memory import AgentMemory
from airunner_services.database.models.conversation_turn import ConversationTurn
from airunner_services.database.models.ai_models import AIModels
from airunner_services.database.models.fhe_key_material import (
    FheKeyMaterial,
)
from airunner_services.database.models.agent_config import AgentConfig
from airunner_services.database.models.airunner_settings import (
    AIRunnerSettings,
)
from airunner_services.database.models.application_settings import (
    ApplicationSettings,
)
from airunner_services.database.models.brush_settings import BrushSettings
from airunner_services.database.models.canvas_document import CanvasDocument
from airunner_services.database.models.canvas_layer import CanvasLayer
from airunner_services.database.models.chatstore import Chatstore
from airunner_services.database.models.chat_session import ChatSession
from airunner_services.database.models.chatbot import Chatbot
from airunner_services.database.models.chatbot_story_event import (
    ChatbotStoryEvent,
)
from airunner_services.database.models.controlnet_model import ControlnetModel
from airunner_services.database.models.controlnet_settings import (
    ControlnetSettings,
)
from airunner_services.database.models.conversation import Conversation
from airunner_services.database.models.drawingpad_settings import (
    DrawingPadSettings,
)
from airunner_services.database.models.document import Document
from airunner_services.database.models.document_chunk import DocumentChunk
from airunner_services.database.models.espeak_settings import EspeakSettings
from airunner_services.database.models.font_setting import FontSetting
from airunner_services.database.models.generator_settings import (
    GeneratorSettings,
)
from airunner_services.database.models.grid_settings import GridSettings
from airunner_services.database.models.image_filter import ImageFilter
from airunner_services.database.models.image_filter_value import (
    ImageFilterValue,
)
from airunner_services.database.models.image_to_image_settings import (
    ImageToImageSettings,
)
from airunner_services.database.models.knowledge_fact import (
    KnowledgeFact,
)
from airunner_services.database.models.knowledge_tag import KnowledgeTag
from airunner_services.database.models.knowledge_fact_tag import (
    KnowledgeFactTag,
)
from airunner_services.database.models.knowledge_fact_relation import (
    KnowledgeFactRelation,
)
from airunner_services.database.models.language_settings import (
    LanguageSettings,
)
from airunner_services.database.models.llm_generator_settings import (
    LLMGeneratorSettings,
)
from airunner_services.database.models.memory_settings import MemorySettings
from airunner_services.database.models.llm_tool import LLMTool
from airunner_services.database.models.mood_history import MoodHistory
from airunner_services.database.models.metadata_settings import (
    MetadataSettings,
)
from airunner_services.database.models.openvoice_settings import (
    OpenVoiceSettings,
)
from airunner_services.database.models.outpaint_settings import (
    OutpaintSettings,
)
from airunner_services.database.models.path_settings import PathSettings
from airunner_services.database.models.pipeline_model import PipelineModel
from airunner_services.database.models.pipeline_call_content import (
    PipelineCallContent,
)
from airunner_services.database.models.prompt_template import PromptTemplate
from airunner_services.database.models.rag_settings import RAGSettings
from airunner_services.database.models.saved_prompt import SavedPrompt
from airunner_services.database.models.schedulers import Schedulers
from airunner_services.database.models.shortcut_keys import ShortcutKeys
from airunner_services.database.models.sound_settings import SoundSettings
from airunner_services.database.models.stt_settings import STTSettings
from airunner_services.database.models.summary import Summary
from airunner_services.database.models.target_directories import (
    TargetDirectories,
)
from airunner_services.database.models.target_files import TargetFiles
from airunner_services.database.models.user import User
from airunner_services.database.models.voice_settings import VoiceSettings
from airunner_services.database.models.whisper_settings import (
    WhisperSettings,
)
from airunner_services.database.models.steam_connection import SteamConnection
from airunner_services.database.models.zimfile import ZimFile
from airunner_services.database.models.lora import Lora
from airunner_services.database.models.embedding import Embedding
from airunner_services.database.models.fine_tuned_model import FineTunedModel
from airunner_services.database.models.project_setting import ProjectSetting
from airunner_services.database.models.curiosity_question import (
    CuriosityQuestion,
)
from airunner_services.database.models.uwu_conversation import UwuConversation
from airunner_services.database.models.conversation_event import (
    ConversationEvent,
)
from airunner_services.database.models.twitch_connection import (
    TwitchConnection,
)
from airunner_services.database.models.itch_connection import (
    ItchConnection,
)
from airunner_services.database.models.email_account import (
    EmailAccount,
)
from airunner_services.database.models.email_sync_checkpoint import (
    EmailSyncCheckpoint,
)
from airunner_services.database.models.email_message import (
    EmailMessage,
)
from airunner_services.database.models.email_body_chunk import (
    EmailBodyChunk,
)
from airunner_services.database.models.email_contact import (
    EmailContact,
)
from airunner_services.database.models.email_stats import (
    EmailStats,
)
from airunner_services.database.models.entity import (
    Entity,
)
from airunner_services.database.models.entity_relationship import (
    EntityRelationship,
)

__all__ = [
    "FheKeyMaterial",
    "ActiveGridSettings",
    "AgentMemory",
    "ConversationTurn",
    "AIModels",
    "AgentConfig",
    "AIRunnerSettings",
    "ApplicationSettings",
    "BrushSettings",
    "CanvasDocument",
    "CanvasLayer",
    "ChatSession",
    "Chatstore",
    "Chatbot",
    "ChatbotStoryEvent",
    "ControlnetModel",
    "ControlnetSettings",
    "Conversation",
    "DrawingPadSettings",
    "Document",
    "DocumentChunk",
    "Embedding",
    "EspeakSettings",
    "FineTunedModel",
    "FontSetting",
    "GeneratorSettings",
    "GridSettings",
    "ImageFilter",
    "ImageFilterValue",
    "ImageToImageSettings",
    "KnowledgeFact",
    "KnowledgeFactRelation",
    "KnowledgeFactTag",
    "KnowledgeTag",
    "LanguageSettings",
    "LLMTool",
    "LLMGeneratorSettings",
    "MoodHistory",
    "Lora",
    "MemorySettings",
    "MetadataSettings",
    "OpenVoiceSettings",
    "OutpaintSettings",
    "PathSettings",
    "PipelineModel",
    "PipelineCallContent",
    "PromptTemplate",
    "RAGSettings",
    "SavedPrompt",
    "Schedulers",
    "ShortcutKeys",
    "SoundSettings",
    "STTSettings",
    "Summary",
    "TargetDirectories",
    "TargetFiles",
    "User",
    "VoiceSettings",
    "WhisperSettings",
    "ZimFile",
    "ProjectSetting",
    "CuriosityQuestion",
    "SteamConnection",
    "TwitchConnection",
    "ItchConnection",
    "EmailAccount",
    "EmailSyncCheckpoint",
    "EmailMessage",
    "EmailBodyChunk",
    "EmailContact",
    "EmailStats",
    "Entity",
    "EntityRelationship",
    "UwuConversation",
    "ConversationEvent",
]
