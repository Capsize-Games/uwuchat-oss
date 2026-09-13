"""Service-owned chatbot model."""

from enum import Enum

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from airunner_services.contract_enums import Gender
from airunner_services.database.base import BaseModel
from airunner_services.settings import (
    AIRUNNER_DEFAULT_CHATBOT_GUARDRAILS_PROMPT,
    AIRUNNER_DEFAULT_CHATBOT_SYSTEM_PROMPT,
    AIRUNNER_DEFAULT_LLM_HF_PATH,
)


class ChatbotCreationStatus(str, Enum):
    """Lifecycle of a background random-chatbot creation job.

    ``ready`` is also the backfilled value for rows created before the
    column existed (no job ever owned them).  ``acknowledged`` is the
    terminal "user has seen the ready notification" state — the client
    transitions to it once the one-time notification is dismissed.
    """

    PENDING = "pending"
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"
    ACKNOWLEDGED = "acknowledged"


class Chatbot(BaseModel):
    """Persisted chatbot persona and model configuration."""

    __tablename__ = "chatbots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, default="Chatbot", unique=True)
    botname = Column(String, default="Computer")
    use_personality = Column(Boolean, default=True)
    use_mood = Column(Boolean, default=True)
    use_guardrails = Column(Boolean, default=True)
    use_system_instructions = Column(Boolean, default=True)
    use_datetime = Column(Boolean, default=True)
    assign_names = Column(Boolean, default=True)
    bot_personality = Column(Text, default="happy. He loves {{ username }}")
    prompt_template = Column(
        Text,
        default="Mistral 7B Instruct: Default Chatbot",
    )
    use_tool_filter = Column(Boolean, default=False)
    use_gpu = Column(Boolean, default=True)
    skip_special_tokens = Column(Boolean, default=True)
    sequences = Column(Integer, default=1)
    seed = Column(BigInteger, default=42)
    random_seed = Column(Boolean, default=True)
    model_version = Column(String, default=AIRUNNER_DEFAULT_LLM_HF_PATH)
    model_type = Column(String, default="llm")
    dtype = Column(String, default="4bit")
    return_result = Column(Boolean, default=True)
    guardrails_prompt = Column(
        Text,
        default=AIRUNNER_DEFAULT_CHATBOT_GUARDRAILS_PROMPT,
    )
    system_instructions = Column(
        Text,
        default=AIRUNNER_DEFAULT_CHATBOT_SYSTEM_PROMPT,
    )
    top_p = Column(Integer, default=900)
    min_length = Column(Integer, default=1)
    max_new_tokens = Column(Integer, default=1000)
    repetition_penalty = Column(Integer, default=100)
    do_sample = Column(Boolean, default=True)
    early_stopping = Column(Boolean, default=True)
    num_beams = Column(Integer, default=1)
    temperature = Column(Integer, default=1000)
    ngram_size = Column(Integer, default=2)
    top_k = Column(Integer, default=10)
    eta_cutoff = Column(Integer, default=10)
    num_return_sequences = Column(Integer, default=1)
    decoder_start_token_id = Column(Integer, default=None)
    use_cache = Column(Boolean, default=True)
    length_penalty = Column(Integer, default=100)
    backstory = Column(Text, default="")
    use_backstory = Column(Boolean, default=True)
    use_weather_prompt = Column(Boolean, default=False)
    allow_narrative_text = Column(Boolean, default=False, nullable=False)
    gender = Column(String, default=Gender.MALE.value)
    species = Column(String, nullable=True)
    knowledge_mode = Column(
        String, default="omniscient", nullable=False
    )
    avatar_emoji = Column(String, nullable=True)
    voice_id = Column(Integer, ForeignKey("voice_settings.id"), nullable=True)
    current = Column(Boolean, default=False)
    attributes = Column(JSON, nullable=True)
    location = Column(JSON, nullable=True)
    language = Column(JSON, nullable=True)
    output_language = Column(String, nullable=True)
    language_proficiency = Column(String, default="fluent", nullable=False)
    species_data = Column(JSON, nullable=True)
    inner_state = Column(JSON, nullable=True)
    identity_core = Column(JSON, nullable=True)
    schedule_data = Column(JSON, nullable=True)
    last_tick_at = Column(DateTime, nullable=True)
    world_tier = Column(String, default="dormant")
    avatar_image = Column(Text, nullable=True)
    banner_image = Column(Text, nullable=True)
    is_online = Column(Boolean, default=True, nullable=False)
    offline_until = Column(DateTime(timezone=True), nullable=True)
    offline_reason = Column(Text, nullable=True)
    has_blocked_user = Column(Boolean, default=False, nullable=False)
    block_reason = Column(Text, nullable=True)
    blocked_by_user = Column(Boolean, default=False, nullable=False)
    is_deceased = Column(Boolean, default=False, nullable=False)
    is_system_bot = Column(Boolean, default=False, nullable=False)
    omnipotent_knowledge = Column(Boolean, default=False, nullable=False)
    death_reason = Column(Text, nullable=True)
    deceased_at = Column(DateTime(timezone=True), nullable=True)
    speech_patterns = Column(Text, nullable=True)
    world_state = Column(JSON, nullable=True)
    voice_samples = Column(JSON, nullable=True)
    creation_status = Column(
        String(32), nullable=False,
        default=ChatbotCreationStatus.READY.value,
    )

    target_files = relationship("TargetFiles", back_populates="chatbot")
    target_directories = relationship(
        "TargetDirectories",
        back_populates="chatbot",
    )

    def to_dataclass(self) -> object:
        """Convert the model instance to its dataclass representation."""
        dataclass_cls = self.get_dataclass()
        data = self.to_dict()
        try:
            data["target_files"] = list(
                getattr(self, "target_files", []) or []
            )
        except Exception:
            data["target_files"] = []
        try:
            data["target_directories"] = list(
                getattr(self, "target_directories", []) or []
            )
        except Exception:
            data["target_directories"] = []
        return dataclass_cls(**data)

    @classmethod
    def make_current(cls, chatbot_id: int) -> None:
        """Mark one chatbot current and clear the current flag on others."""
        for chatbot in Chatbot.objects.filter_by(current=True) or []:
            Chatbot.objects.update(chatbot.id, current=False)
        Chatbot.objects.update(chatbot_id, current=True)


__all__ = ["Chatbot", "ChatbotCreationStatus"]
