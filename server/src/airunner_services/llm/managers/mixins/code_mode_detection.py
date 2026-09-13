"""Shared code-mode detection for the agentic-loop framework layer.

UwUchat's code mode (``projects.<project>.server.code_mode_service``)
is a per-conversation toggle.  Several framework components — the
post-tool instruction helper, the agentic iteration guard, the
LangGraph recursion-limit config — must all agree on whether the
current conversation is in code mode, or they will fight each other
(e.g. one component force-stops while another tells the model to keep
going).

Every call site used to re-implement the same guarded project import.
This module is the single home for that lookup so the guard, the
streaming config, and any future component agree by construction.
"""

from __future__ import annotations

from typing import Any


def code_mode_active_for_owner(owner: Any) -> bool:
    """Return True when *owner*'s current conversation has code mode on.

    *owner* is the LLM manager or workflow manager building the
    conversation.  The conversation id is read from
    ``code_mode_active_for_owner`` in the project module, which resolves
    it the same way every other component does (manager's own
    ``_conversation_id``, falling back to the workflow manager's).

    Any import error, missing project, or non-UwUchat deployment
    returns False — a pure no-op.  This is the SAME guarded-project
    pattern the tool filter, prompt builder, and post-tool helper use.
    """
    try:
        import importlib
        import os

        project = os.environ.get("AIRUNNER_PROJECT", "")
        if not project:
            from airunner_services.conf import settings

            project = getattr(settings, "AIRUNNER_PROJECT", "") or ""
        if not project:
            return False
        mod = importlib.import_module(
            f"projects.{project}.server.code_mode_service"
        )
        func = getattr(mod, "code_mode_active_for_owner", None)
        if func is None:
            return False
        return bool(func(owner))
    except (ImportError, AttributeError, TypeError):
        return False
