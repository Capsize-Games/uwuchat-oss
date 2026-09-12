"""Complexity-tier model swapping helpers.

Extracted from ``generation_execution_support``.  Temporarily swaps
the DIALOGUE chat model for the request's complexity tier and restores
it after the turn.
"""

from __future__ import annotations

from airunner_services.llm.pipeline_loader import pipeline_config


def _apply_dialogue_tier_model(owner) -> bool:
    """Temporarily swap the DIALOGUE chat model for this request's tier.

    Returns True if the model was swapped (caller must restore).
    """
    try:
        tier = getattr(owner, "_complexity_tier", "standard")
        cfg = pipeline_config("DIALOGUE")
        tiers: list = cfg.get("tiers", [])
        if not tiers:
            return False
        for t in tiers:
            if isinstance(t, dict) and t.get("name") == tier:
                tier_model_name = t.get("model")
                if tier_model_name:
                    chat_model = getattr(owner, "_chat_model", None)
                    if chat_model is not None and hasattr(
                        chat_model, "model_name"
                    ):
                        owner._dialogue_original_model = (
                            chat_model.model_name
                        )
                        chat_model.model_name = tier_model_name
                        return True
        return False
    except Exception:
        return False


def _restore_dialogue_model(owner) -> None:
    """Restore the original DIALOGUE model name after the request."""
    try:
        chat_model = getattr(owner, "_chat_model", None)
        original = getattr(owner, "_dialogue_original_model", None)
        if chat_model is not None and original is not None:
            chat_model.model_name = original
        owner._dialogue_original_model = None
    except Exception:
        pass
