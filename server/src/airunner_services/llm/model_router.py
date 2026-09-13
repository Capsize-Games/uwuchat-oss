"""LLM model router: maps function keys to provider/model configs."""

from __future__ import annotations

from copy import copy
from typing import Any, Dict, Optional

from airunner_services.contract_enums import ModelService


class ModelRouter:
    """Route named LLM function keys to provider/model configurations."""

    def __init__(self, routing: Dict[str, Dict[str, str]]) -> None:
        self._routing = routing

    def rule(self, key: str) -> Dict[str, str]:
        """Return the routing rule for *key*, or an empty dict."""
        return self._routing.get(key, {})

    def apply_to_settings(self, key: str, settings: Any) -> bool:
        """Mutate *settings* in-place to match the rule for *key*.

        Returns True when a rule was found and applied.
        """
        rule = self.rule(key)
        if not rule:
            return False
        _apply_rule(rule, settings)
        return True

    def build_model(
        self,
        key: str,
        base_settings: Any,
        chatbot: Optional[Any] = None,
    ) -> Optional[Any]:
        """Create and return a chat model for *key*.

        Copies *base_settings*, applies the routing rule, and delegates
        to :class:`ChatModelFactory`.  Returns ``None`` when no rule
        exists for *key*.

        Pipeline-level ``max_tokens`` is read from the rule and passed
        as a keyword override so each pipeline gets its own budget
        instead of silently inheriting the 500-token builder default.
        """
        rule = self.rule(key)
        if not rule:
            return None
        overridden = copy(base_settings)
        _apply_rule(rule, overridden)
        max_tokens_str = rule.get("max_tokens")
        max_tokens_override: Optional[int] = None
        if max_tokens_str is not None:
            try:
                max_tokens_override = int(max_tokens_str)
            except (TypeError, ValueError):
                pass
        from airunner_services.llm.adapters import ChatModelFactory

        return ChatModelFactory.create_from_settings(
            llm_settings=overridden,
            chatbot=chatbot,
            max_tokens_override=max_tokens_override,
        )

    def build_specialized(
        self,
        keys: tuple[str, ...],
        base_settings: Any,
        chatbot: Optional[Any] = None,
    ) -> dict[str, Any]:
        """Build chat models for every key in *keys* that differs from
        DIALOGUE's rule.

        Returns ``{key: model}`` for keys that produced a model.
        Callers merge the result into their own
        ``_specialized_chat_models`` dict.
        """
        dialogue_rule = self.rule("DIALOGUE")
        specialized: dict[str, Any] = {}
        for key in keys:
            rule = self.rule(key)
            # A key with no provider of its own (framework-default-only,
            # never configured by the project) has nothing that "differs
            # from DIALOGUE" to build — it correctly falls back to the
            # DIALOGUE model at call time instead.
            if not rule or not rule.get("provider") or rule == dialogue_rule:
                continue
            model = self.build_model(key, base_settings, chatbot)
            if model:
                specialized[key] = model
        return specialized


def _apply_rule(rule: Dict[str, str], settings: Any) -> None:
    """Set provider flags and model name on *settings* from *rule*."""
    provider = rule.get("provider", ModelService.LOCAL.value)
    settings.use_openrouter = provider == ModelService.OPENROUTER.value
    settings.use_ollama = provider == ModelService.OLLAMA.value
    settings.use_openai = provider == ModelService.OPENAI.value
    settings.use_deepinfra = provider == ModelService.DEEPINFRA.value
    settings.use_local_llm = provider == ModelService.LOCAL.value
    model_name = rule.get("model")
    if not model_name:
        return
    if provider == ModelService.OPENROUTER.value:
        settings.model = model_name
    elif provider == ModelService.OLLAMA.value:
        settings.ollama_model = model_name
    elif provider == ModelService.OPENAI.value:
        settings.openai_model = model_name
    elif provider == ModelService.DEEPINFRA.value:
        settings.deepinfra_model = model_name


def _dialogue_routing_subset(pipeline: dict) -> dict:
    """Extract the keys ModelRouter needs from a PIPELINE_CONFIG."""
    keys = (
        "DIALOGUE", "TOOL_CLASSIFICATION",
        "SUMMARIZATION", "STATELESS", "KNOWLEDGE",
        "RESPONSE", "TOOL_EXECUTION",
        "PROMPT_REWRITE",
    )
    subset: dict = {}
    for k in keys:
        if k not in pipeline:
            continue
        val = dict(pipeline[k])
        max_tokens = val.get("max_tokens")
        if max_tokens is not None:
            val["max_tokens"] = str(int(max_tokens))
        subset[k] = val
    return subset


def load_project_router() -> Optional[ModelRouter]:
    """Build a :class:`ModelRouter` from the active project pipeline config.

    Uses :mod:`pipeline_loader` so all routing is sourced from the single
    merged pipeline dict (framework defaults + project overrides).
    """
    try:
        from airunner_services.llm.pipeline_loader import load_pipeline
        pipeline = load_pipeline()
        subset = _dialogue_routing_subset(pipeline)
        if subset:
            return ModelRouter(subset)
    except Exception:
        pass
    return None


__all__ = ["ModelRouter", "load_project_router"]
