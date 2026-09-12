"""Prompt-rewrite stage helper.

Extracted from ``request_handling_mixin``.  Runs the prompt-rewrite
stage (when a PROMPT_REWRITE model is available) and returns rewritten
text, never mutating the user's original prompt.
"""

from __future__ import annotations


def _maybe_rewrite_data_prompt(owner, data: dict) -> str | None:
    """Run the prompt-rewrite stage, returning rewritten text or None.

    Reads ``data["request_data"]["prompt"]`` (never mutates it) and
    returns the rewritten version when applicable.  Returns ``None``
    when no rewrite is needed or the stage fails — the caller keeps
    using the original prompt.
    """
    specialized = getattr(owner, "_specialized_chat_models", {})
    rewrite_model = specialized.get("PROMPT_REWRITE")
    if rewrite_model is None:
        return None

    prompt = data["request_data"]["prompt"]
    try:
        import importlib
        import os

        project = os.environ.get("AIRUNNER_PROJECT", "")
        if not project:
            from airunner_services.conf import settings

            project = getattr(settings, "AIRUNNER_PROJECT", "") or ""
        if not project:
            return None
        mod = importlib.import_module(
            f"projects.{project}.server.prompt_rewrite_stage"
        )
        run_stage = mod.run_prompt_rewrite_stage
    except ImportError:
        owner.logger.debug(
            "Prompt rewrite: module not importable, "
            "passing original through",
        )
        return None

    try:
        rewritten, reason = run_stage(
            chat_model=rewrite_model,
            prompt=prompt,
        )
        if rewritten is not None and rewritten != prompt:
            owner.logger.info(
                "Prompt rewrite: %s — '%s' → '%s'",
                reason, prompt[:60], rewritten[:60],
            )
            return rewritten
        if reason and reason != "scope acceptable":
            owner.logger.debug(
                "Prompt rewrite: %s — keeping original", reason,
            )
        return None
    except Exception:
        owner.logger.debug(
            "Prompt rewrite: stage failed, "
            "passing original through",
            exc_info=True,
        )
        return None
