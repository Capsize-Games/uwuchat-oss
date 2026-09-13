"""Service-owned settings for Large Language Model functionality."""

import os
from dataclasses import dataclass

if os.environ.get("DEV_ENV", "1") == "1":
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

from airunner_services.settings import (
    AIRUNNER_LLM_AGENT_MAX_FUNCTION_CALLS,
    AIRUNNER_LLM_AGENT_SUMMARIZE_AFTER_N_TURNS,
    AIRUNNER_LLM_AGENT_UPDATE_MOOD_AFTER_N_TURNS,
    AIRUNNER_LLM_MODEL,
    AIRUNNER_LLM_OPENROUTER_MODEL,
    AIRUNNER_LLM_PERFORM_ANALYSIS,
    AIRUNNER_LLM_PERFORM_CONVERSATION_RAG,
    AIRUNNER_LLM_PERFORM_CONVERSATION_SUMMARY,
    AIRUNNER_LLM_PRINT_SYSTEM_PROMPT,
    AIRUNNER_LLM_PROVIDER,
    AIRUNNER_LLM_UPDATE_USER_DATA_ENABLED,
    AIRUNNER_LLM_USE_CHATBOT_MOOD,
    AIRUNNER_LLM_USE_WEATHER_PROMPT,
    AIRUNNER_OLLAMA_BASE_URL,
)

# AIRUNNER_LLM_PROVIDER selects which use_* flag starts True. Empty
# (desktop-app default) keeps the historical local-GGUF behavior.
_USE_OPENROUTER = AIRUNNER_LLM_PROVIDER == "openrouter"
_USE_OLLAMA = AIRUNNER_LLM_PROVIDER == "ollama"
_USE_OPENAI = AIRUNNER_LLM_PROVIDER == "openai"
_USE_DEEPINFRA = AIRUNNER_LLM_PROVIDER == "deepinfra"
_USE_LOCAL_LLM = AIRUNNER_LLM_PROVIDER in ("", "local")


@dataclass
class LLMSettings:
    """Configuration options for local and API-backed LLM usage."""

    use_weather_prompt: bool = AIRUNNER_LLM_USE_WEATHER_PROMPT
    update_mood_after_n_turns: int = (
        AIRUNNER_LLM_AGENT_UPDATE_MOOD_AFTER_N_TURNS
    )
    summarize_after_n_turns: int = AIRUNNER_LLM_AGENT_SUMMARIZE_AFTER_N_TURNS
    perform_conversation_summary: bool = (
        AIRUNNER_LLM_PERFORM_CONVERSATION_SUMMARY
    )
    max_function_calls: int = AIRUNNER_LLM_AGENT_MAX_FUNCTION_CALLS
    model: str = AIRUNNER_LLM_OPENROUTER_MODEL
    print_llm_system_prompt: bool = AIRUNNER_LLM_PRINT_SYSTEM_PROMPT
    llm_perform_analysis: bool = AIRUNNER_LLM_PERFORM_ANALYSIS
    update_user_data_enabled: bool = AIRUNNER_LLM_UPDATE_USER_DATA_ENABLED
    use_chatbot_mood: bool = AIRUNNER_LLM_USE_CHATBOT_MOOD
    perform_conversation_rag: bool = AIRUNNER_LLM_PERFORM_CONVERSATION_RAG
    auto_extract_knowledge: bool = True

    core_facts_count: int = 10
    rag_facts_count: int = 5
    use_rag_for_facts: bool = True

    use_local_llm: bool = _USE_LOCAL_LLM
    use_openrouter: bool = _USE_OPENROUTER
    use_ollama: bool = _USE_OLLAMA
    use_openai: bool = _USE_OPENAI
    use_deepinfra: bool = _USE_DEEPINFRA

    openrouter_api_key: str = ""
    openai_api_key: str = ""
    deepinfra_api_key: str = ""
    deepinfra_model: str = "mistralai/Mistral-Nemo-Instruct-2407"

    use_yarn: bool = False
    yarn_target_context: int = 0

    include_health_disclaimer: bool = True

    enable_thinking: bool = True

    ollama_model: str = AIRUNNER_LLM_MODEL or "llama2"
    ollama_base_url: str = AIRUNNER_OLLAMA_BASE_URL

    openai_model: str = "gpt-4"

    @property
    def use_api(self) -> bool:
        """Return whether any remote API backend is active."""
        return bool(
            getattr(self, "use_openrouter", False)
            or getattr(self, "use_openai", False)
            or getattr(self, "use_ollama", False)
            or getattr(self, "use_deepinfra", False)
        )


__all__ = ["LLMSettings"]
