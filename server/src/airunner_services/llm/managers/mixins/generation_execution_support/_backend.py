"""Active-chat-model backend detection helpers.

Extracted from ``generation_execution_support``.  Answers questions
about the active chat model(s): which providers are in use, whether a
restrictive ``tool_choice`` is bound, and whether the active model
supports reasoning parameters.
"""

from __future__ import annotations


# Model name prefixes known to support the OpenRouter reasoning
# (thinking) extra_body parameter.  Sending it to unsupported
# providers (e.g. Google Gemini) causes mid-stream errors.
# Additions must be verified with a live streaming test first —
# see scripts/test_reasoning_param.py.
_REASONING_MODEL_PREFIXES = (
    "deepseek/",
    "anthropic/",
)


def _active_chat_models(owner):
    """Yield the LLM manager model and the workflow manager model.

    Tools are bound on the *workflow manager's* _chat_model, not the LLM
    manager's.  Both need to be checked so detection works regardless of
    which layer holds the active binding.
    """
    yield getattr(owner, "_chat_model", None)
    wm = getattr(owner, "_workflow_manager", None)
    if wm is not None:
        yield getattr(wm, "_chat_model", None)


def _has_tool_choice(owner) -> bool:
    """Return True when a specific tool_choice is active on any chat model.

    bind_tools(tool_choice=...) stores the choice in the RunnableBinding's
    kwargs dict.  Checks both the LLM manager and workflow manager models
    because tools are bound at the workflow manager level.
    """
    for model in _active_chat_models(owner):
        if model is None:
            continue
        binding_kwargs = getattr(model, "kwargs", {}) or {}
        if binding_kwargs.get("tool_choice") is not None:
            return True
    return False


def _is_openai_backend(owner) -> bool:
    """Return True when any active chat model rejects HF-only kwargs.

    Covers OpenAI-compatible clients (OpenAI, OpenRouter — both
    ``ChatOpenAI``) and Ollama (``ChatOllama``): all three reject
    unknown top-level generation kwargs (``do_sample``, ``eta_cutoff``,
    etc.) that only the local HuggingFace/llama-cpp backends
    understand, so ``_normalize_generation_kwargs`` must strip them
    before the call. ``bind_tools()`` wraps the model in a
    ``RunnableBinding``; unwrap one level to reach the actual model
    instance.  Checks both the LLM manager and workflow manager models.
    """
    try:
        from langchain_openai import ChatOpenAI

        try:
            from langchain_ollama import ChatOllama

            api_model_classes: tuple = (ChatOpenAI, ChatOllama)
        except ImportError:
            api_model_classes = (ChatOpenAI,)

        for model in _active_chat_models(owner):
            if model is None:
                continue
            if isinstance(model, api_model_classes):
                return True
            bound = getattr(model, "bound", None)
            if isinstance(bound, api_model_classes):
                return True
        return False
    except ImportError:
        return False


def _model_supports_reasoning(owner) -> bool:
    """Return True when the active model is known to support reasoning.

    Only models whose name starts with a known reasoning-capable prefix
    receive the extra_body.reasoning parameter.  Sending it to
    unsupported providers (e.g. Google Gemini via OpenRouter) causes
    mid-stream JSON parse errors.
    """
    for model in _active_chat_models(owner):
        if model is None:
            continue
        model_name = getattr(model, "model", None) or ""
        if model_name.startswith(_REASONING_MODEL_PREFIXES):
            return True
    return False
