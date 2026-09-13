"""Request orchestration for LLM generation.

Decomposed into focused mixin modules:

- ``_conversation`` — conversation/agent preparation
- ``_overrides`` — dtype/service/thinking/reasoning overrides
- ``_rag`` — attached-document RAG preparation
- ``_tooling`` — tool defaults and per-request tool filtering
- ``_stages`` — pre-flight and cheap tool-execution stage
- ``_main`` — the ``handle_request`` orchestrator and
  ``_maybe_rewrite_data_prompt``

``RequestHandlingMixin`` is the composed public class; all existing
importers keep working unchanged.
"""

from __future__ import annotations

from airunner_services.llm.managers.mixins.request_handling_mixin._conversation import (
    RequestConversationMixin,
)
from airunner_services.llm.managers.mixins.request_handling_mixin._main import (
    RequestHandlingCoreMixin,
)
from airunner_services.llm.managers.mixins.request_handling_mixin._overrides import (
    RequestOverrideMixin,
)
from airunner_services.llm.managers.mixins.request_handling_mixin._rewrite import (
    _maybe_rewrite_data_prompt,
)
from airunner_services.llm.managers.mixins.request_handling_mixin._rag import (
    RequestRagMixin,
)
from airunner_services.llm.managers.mixins.request_handling_mixin._stages import (
    RequestStageMixin,
)
from airunner_services.llm.managers.mixins.request_handling_mixin._tooling import (
    RequestToolingMixin,
)
from airunner_services.llm.managers.mixins.request_handling_mixin._dialogue_routing import (
    RequestDialogueRoutingMixin,
)


class RequestHandlingMixin(
    RequestHandlingCoreMixin,
    RequestConversationMixin,
    RequestOverrideMixin,
    RequestRagMixin,
    RequestStageMixin,
    RequestToolingMixin,
    RequestDialogueRoutingMixin,
):
    """Coordinate request-time model, tool, and RAG preparation."""


__all__ = [
    "RequestConversationMixin",
    "RequestDialogueRoutingMixin",
    "RequestHandlingCoreMixin",
    "RequestHandlingMixin",
    "RequestOverrideMixin",
    "RequestRagMixin",
    "RequestStageMixin",
    "RequestToolingMixin",
    "_maybe_rewrite_data_prompt",
]
