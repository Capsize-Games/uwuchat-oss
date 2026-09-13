"""Per-conversation DIALOGUE routing mixin (Decision B hook).

The framework asks the active project's optional ``dialogue_routing``
module to resolve DIALOGUE's provider/model per conversation at request
time — the same guarded-project-import pattern as ``tool_execution_stage``
and ``prompt_builder._code_mode_active``. Projects that don't define the
module (or can't be imported) keep the static pipeline default, so this
is a pure no-op for any non-UwUchat deployment.

The hook mutates ``self.llm_settings`` in place. The caller
(``handle_request``) rebuilds the chat model via the existing
``unload()``/``load()`` machinery when the settings changed, so the
model, workflow manager, and tool bindings are all constructed from the
routed settings — no manual model swapping.
"""

from __future__ import annotations

import importlib
import os
from typing import Any


class RequestDialogueRoutingMixin:
    """Apply per-conversation DIALOGUE provider/model routing."""

    def _apply_dialogue_conversation_routing(
        self, conversation_id: int | None,
        llm_request: Any = None,
    ) -> bool:
        """Mutate ``self.llm_settings`` for the request's conversation.

        *conversation_id* is the request's own conversation id (from the
        incoming data dict) — NOT ``_workflow_manager._conversation_id``,
        which is only set later during conversation preparation.

        *llm_request*, when available, is passed to the resolver so it
        can apply request-scoped adjustments (e.g. disabling thinking
        for the local chat daemon).

        Returns True when the settings changed (the caller must rebuild
        the chat model). Never raises — a lookup/import failure keeps the
        default routing and logs.
        """
        resolve = self._dialogue_routing_resolver()
        if resolve is None:
            return False

        llm_settings = getattr(self, "llm_settings", None)
        if llm_settings is None:
            return False

        try:
            changed = bool(
                resolve(llm_settings, conversation_id, llm_request)
            )
        except TypeError:
            # Resolver with the older two-arg signature — tolerate it.
            try:
                changed = bool(resolve(llm_settings, conversation_id))
            except Exception:
                self.logger.exception(
                    "dialogue_routing failed; keeping default routing"
                )
                return False
        except Exception:
            self.logger.exception(
                "dialogue_routing failed; keeping default routing"
            )
            return False
        return changed

    @staticmethod
    def _dialogue_routing_resolver():
        """Return the project's resolver callable, or None.

        Guarded import of ``projects.<active>.server.dialogue_routing``
        — absent module (or no active project) returns None so the
        framework never hard-depends on a project's routing module.
        """
        try:
            project = os.environ.get("AIRUNNER_PROJECT", "")
            if not project:
                from airunner_services.conf import settings

                project = getattr(settings, "AIRUNNER_PROJECT", "") or ""
            if not project:
                return None
            mod = importlib.import_module(
                f"projects.{project}.server.dialogue_routing"
            )
            return getattr(mod, "resolve_dialogue_llm_settings", None)
        except ImportError:
            return None
        except Exception:
            return None


__all__ = ["RequestDialogueRoutingMixin"]
