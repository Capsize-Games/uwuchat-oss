"""Minimal cloud model manager — no torch/transformers/edge deps."""

from __future__ import annotations

from typing import Any

from airunner_services.llm.adapters.chat_model_factory import ChatModelFactory
from airunner_services.llm.llm_settings import LLMSettings
from airunner_services.llm.managers.mixins.conversation_management_mixin import (
    ConversationManagementMixin,
)
from airunner_services.llm.managers.mixins.generation_mixin import (
    GenerationMixin,
)
from airunner_services.llm.managers.mixins.property_mixin import PropertyMixin
from airunner_services.llm.managers.mixins.request_handling_mixin import (
    RequestHandlingMixin,
)
from airunner_services.llm.managers.mixins.system_prompt_mixin import (
    SystemPromptMixin,
)
from airunner_services.llm.managers.mixins.tool_classification_mixin import (
    ToolClassificationMixin,
)
from airunner_services.llm.managers.mixins.tool_filtering_mixin import (
    ToolFilteringMixin,
)
from airunner_services.llm.tool_manager import ToolManager
from airunner_services.llm_workflow_events import NullLLMToolActionHandler
from airunner_services.utils.application.runtime_context_mixin import (
    RuntimeContextMixin,
)


class CloudModelManager(
    RuntimeContextMixin,
    ConversationManagementMixin,
    GenerationMixin,
    PropertyMixin,
    RequestHandlingMixin,
    SystemPromptMixin,
    ToolClassificationMixin,
    ToolFilteringMixin,
):
    """Lightweight model manager for cloud API providers.

    Implements a cloud-compatible subset of the LLMModelManager
    interface — no edge model loading, no torch, no transformers.
    """

    def __init__(self) -> None:
        self.llm_settings = LLMSettings()
        self.logger = _cloud_logger()
        self._chat_model = None
        self._workflow_manager = None
        self._tool_manager = None
        self._pii_vault = None
        self._current_request_id = None
        self._interrupted = False
        self._pre_prompt_knowledge = ""
        self._pre_prompt_self_knowledge = ""
        self._assistant_turn_index = 0
        self._system_prompt = ""
        self._tools = []
        self._max_history_tokens = 8192
        self._token_counter = None
        self._current_model_path = ""
        self._model_status: dict[Any, Any] = {}
        self.llm_request = None
        self._chatbot: Any = None
        self._specialized_chat_models: dict = {}
        from airunner_services.llm.model_router import load_project_router
        self._model_router = load_project_router()
        super().__init__()

    # ------------------------------------------------------------------
    # Cloud overrides — skip edge-specific model-path validation
    # ------------------------------------------------------------------

    @property
    def model_path(self) -> str:
        """Return empty — cloud providers have no local model path."""
        return ""

    @property
    def chatbot(self) -> Any:
        """Return the cached chatbot or fall back to the DB resolver."""
        if self._chatbot is not None:
            return self._chatbot
        from airunner_services.llm.get_chatbot import get_chatbot
        return get_chatbot()

    # ------------------------------------------------------------------
    # Model lifecycle
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Create ChatModel, ToolManager, and WorkflowManager for cloud."""
        if self._chat_model is not None:
            return
        self._validate_cloud_imports()
        # Read DIALOGUE's per-pipeline max_tokens override.
        # ChatModelFactory.create_from_settings has a dedicated
        # max_tokens_override parameter exactly for this — it
        # threads through to build_provider_runtime_config.
        max_tokens_override: int | None = None
        try:
            from airunner_services.llm.pipeline_loader import (
                pipeline_config,
            )
            dialogue_cfg = pipeline_config("DIALOGUE")
            mt = dialogue_cfg.get("max_tokens")
            if mt is not None:
                max_tokens_override = int(mt)
        except Exception:
            pass
        try:
            self.logger.info("CloudModelManager: creating chat model")
            self._chat_model = ChatModelFactory.create_from_settings(
                llm_settings=self.llm_settings,
                model=None,
                tokenizer=None,
                chatbot=getattr(self, "chatbot", None),
                model_path=None,
                gguf_runtime_profile=None,
                max_tokens_override=max_tokens_override,
            )
        except Exception as exc:
            self.logger.error("Error creating ChatModel: %s", exc)
            self._chat_model = None
            return

        self._load_specialized_models()
        self._load_tool_manager()
        self._load_workflow_manager()

    def unload(self) -> None:
        """Release cloud components."""
        if self._workflow_manager is not None:
            self._workflow_manager = None
        if self._tool_manager is not None:
            self._tool_manager = None
        if self._chat_model is not None:
            self._chat_model = None
        if hasattr(self, "_specialized_chat_models"):
            self._specialized_chat_models.clear()

    def _load_specialized_models(self) -> None:
        """Pre-build chat models for non-DIALOGUE pipeline keys.

        Cloud counterpart of component_loader_mixin._load_specialized_models.
        Delegates to :meth:`ModelRouter.build_specialized` so the loop
        body lives in one place.

        Creates separate ChatOpenAI instances for TOOL_CLASSIFICATION,
        SUMMARIZATION, STATELESS, KNOWLEDGE, RESPONSE, and
        TOOL_EXECUTION when their routing differs from DIALOGUE.
        Without these, all pipeline calls fall back to the DIALOGUE model.
        """
        router = getattr(self, "_model_router", None)
        if not router:
            return
        specialized = router.build_specialized(
            keys=(
                "TOOL_CLASSIFICATION", "SUMMARIZATION", "STATELESS",
                "KNOWLEDGE", "RESPONSE", "TOOL_EXECUTION",
                "PROMPT_REWRITE",
            ),
            base_settings=self.llm_settings,
            chatbot=getattr(self, "chatbot", None),
        )
        if not hasattr(self, "_specialized_chat_models"):
            self._specialized_chat_models = {}
        self._specialized_chat_models.update(specialized)

    def do_interrupt(self) -> None:
        """Interrupt the current generation."""
        self._interrupted = True

    # ------------------------------------------------------------------
    # Internal component loaders (no torch dependency)
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_cloud_imports() -> None:
        """Fail fast with a clear message if cloud dependencies are missing.

        Prevents the cryptic ``No module named 'langchain_openai'`` error
        from surfacing on the first user request.  Instead the server will
        log a clear installation instruction at load time.
        """
        try:
            import importlib

            importlib.import_module("langchain_openai")
        except ImportError:
            raise ImportError(
                "langchain-openai is required for cloud LLM support. "
                "Install with: pip install langchain-openai>=0.3.0"
            )

    def _load_tool_manager(self) -> None:
        """Create ToolManager with null event handlers for cloud."""
        if self._tool_manager is not None:
            return
        try:
            self._tool_manager = ToolManager(
                rag_manager=self,
                tool_action_handler=NullLLMToolActionHandler(),
            )
            self.logger.info("Tool manager loaded for cloud")
        except Exception as exc:
            self.logger.error(
                "Error loading tool manager: %s", exc, exc_info=True
            )
            self._tool_manager = None

    def _load_workflow_manager(self) -> None:
        """Create WorkflowManager for cloud API execution."""
        if self._workflow_manager is not None:
            return
        if not self._chat_model:
            self.logger.error(
                "Cannot load workflow manager: ChatModel not loaded"
            )
            return

        try:
            from airunner_services.llm.workflow_manager import (
                WorkflowManager,
            )

            tools_to_use = None
            if self.supports_function_calling and self.tools:
                tools_to_use = self.tools

            # Build a dedicated response model (e.g. Haiku) when the
            # project's routing config includes a RESPONSE key.
            response_model = None
            try:
                from airunner_services.llm.model_router import (
                    load_project_router,
                )
                router = load_project_router()
                if router is None:
                    self.logger.info(
                        "[RESPONSE] load_project_router returned None"
                    )
                else:
                    response_rule = router.rule("RESPONSE")
                    dialogue_rule = router.rule("DIALOGUE")
                    self.logger.info(
                        "[RESPONSE] RESPONSE rule: %s, DIALOGUE: %s",
                        response_rule.get("model", "missing"),
                        dialogue_rule.get("model", "missing"),
                    )
                    if (
                        response_rule
                        and dialogue_rule
                        and response_rule != dialogue_rule
                    ):
                        response_model = router.build_model(
                            "RESPONSE",
                            self.llm_settings,
                            getattr(self, "chatbot", None),
                        )
                        if response_model:
                            self.logger.info(
                                "[RESPONSE] Created: %s",
                                type(response_model).__name__,
                            )
                        else:
                            self.logger.warning(
                                "[RESPONSE] build_model returned None"
                            )
                    else:
                        self.logger.info(
                            "[RESPONSE] Skipped — rules equal or missing"
                        )
            except Exception as exc:
                self.logger.warning(
                    "[RESPONSE] Error: %s", exc
                )

            from airunner_services.llm_workflow_events import (
                resolve_llm_workflow_event_sink,
            )
            event_sink = resolve_llm_workflow_event_sink(self)
            self._event_sink = event_sink
            self.logger.info(
                "[MODEL] chat_model.model_name=%s response_model=%s",
                getattr(self._chat_model, "model_name", "?"),
                getattr(response_model, "model_name", None)
                if response_model else "None",
            )
            self._workflow_manager = WorkflowManager(
                system_prompt=self.system_prompt,
                chat_model=self._chat_model,
                tools=tools_to_use,
                max_history_tokens=8000,
                conversation_id=None,
                llm_settings=self.llm_settings,
                chatbot=getattr(self, "chatbot", None),
                event_sink=event_sink,
                response_model=response_model,
                tool_manager=self._tool_manager,
            )
            self.logger.info("Workflow manager loaded for cloud")
        except Exception as exc:
            self.logger.error(
                "Error loading workflow manager: %s", exc, exc_info=True
            )
            self._workflow_manager = None

    def _unload_tool_manager(self) -> None:
        """Release the tool manager (called by ConversationManagementMixin)."""
        if self._tool_manager is not None:
            self._tool_manager = None

    def get_document_context(
        self, prompt: str, document_ids: list[int], k: int = 5
    ) -> str:
        """Return RAG document context for the given prompt.

        Cloud path returns empty string — document injection is not
        supported for cloud providers. The ``tool`` RAG strategy
        (default) is preferred.
        """
        return ""


def _cloud_logger():
    import logging
    return logging.getLogger("airunner_services.cloud.model_manager")
