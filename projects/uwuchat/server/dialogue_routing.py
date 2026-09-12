"""Per-conversation DIALOGUE provider/model routing (Decision B).

Chat and code models are independently configurable. The chat model is
the ``CHAT_DAEMON_URL`` / ``CHAT_DAEMON_MODEL`` below (env-overridable);
the code model is the separate ``HEADLESSCODE_OLLAMA_URL`` the
headlesscode sidecar uses for code-mode sessions. The two may point at
the same daemon (e.g. Qwen3-14B serving both chat and code) — the GPU
switch (``gpu_inference_mode.apply_code_mode``) no-ops when the two
daemons are the same container.

DIALOGUE (the main UwUChat chat) always uses the local chat daemon —
independent of code mode. When the pipeline is ALREADY routed to ollama
via the framework env override (``AIRUNNER_LLM_PROVIDER=ollama`` +
``AIRUNNER_OLLAMA_BASE_URL`` — the LAN/staging deployment style), this
hook is a no-op: the env-driven ``PIPELINE_CONFIG`` is authoritative and
already points at the chat daemon, so per-conversation overrides would
only fight it (and the container-name URL it would substitute is
unreachable from a remote staging host).

The framework's ``ModelRouter`` applies DIALOGUE's rule to
``llm_settings`` once per request at ``handle_request`` → ``load()`` —
but the rule itself comes from the static ``PIPELINE_CONFIG`` dict
(``ai_pipeline.py``), which is process-lifetime. This module is the
per-conversation hook: the framework (via a guarded project import, the
same pattern as ``tool_execution_stage``) asks it to mutate
``llm_settings`` in place for the conversation currently being generated
for.

Scope note (from the plan): this is a single-operator local dev
environment; "is code mode on" means "is code mode on for the ONE
conversation currently being generated for". Concurrent conversations
with different code-mode states are a known limitation, not solved here.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# The local chat daemon as seen from inside the server container —
# reached by container name over the daemon's compose network (see
# deploy/local/daemons/chat-daemon/docker-compose.yml and
# docker-compose.code-harness-local.yml). The daemon's ollama-compat
# layer ignores the requested model name and serves whatever GGUF is
# loaded, so the model string is cosmetic.
#
# Override both to point chat at a different local daemon (e.g. the
# Qwen3-14B coder daemon: UWUCHAT_CHAT_DAEMON_URL=http://code-daemon-daemon-1:11434
# UWUCHAT_CHAT_DAEMON_MODEL=qwen3-14b). "Same daemon for chat and code"
# is exactly the case where the GPU switch must not swap.
CHAT_DAEMON_URL = os.getenv(
    "UWUCHAT_CHAT_DAEMON_URL", "http://lan-daemon-daemon-1:11434"
)
CHAT_DAEMON_MODEL = os.getenv(
    "UWUCHAT_CHAT_DAEMON_MODEL", "qwen3.5-9b:latest"
)


def resolve_dialogue_llm_settings(
    llm_settings: Any,
    conversation_id: int | None,
    llm_request: Any = None,
) -> bool:
    """Mutate *llm_settings* (and optionally *llm_request*) in place,
    returning True when anything changed.

    Chat and code are independent: the chat model never depends on the
    conversation's code-mode state. When the pipeline is already routed
    to ollama (env-driven ``AIRUNNER_LLM_PROVIDER=ollama`` — the
    LAN/staging deployment), nothing to do. Otherwise the static cloud
    default is pointed at the local chat daemon — the local-dev default
    where chat runs on a local GGUF daemon.

    Code mode itself only swaps the *prompt* (``code_mode_active_for_owner``)
    and the headlesscode session backend (``HEADLESSCODE_OLLAMA_URL``) —
    it does not move DIALOGUE between providers. The GPU switch
    (``gpu_inference_mode``) arbitrates the two daemons when the chat and
    code models are different containers, and no-ops when they are the
    same daemon.

    *llm_request*, when provided, is left untouched: thinking stays
    enabled on the local chat daemon.  (A pre-Aug-19 daemon mishandled
    ``think=true`` and returned the "empty reply" fallback string, which
    is why thinking was briefly force-disabled here; the daemon's
    ollama-compat layer has since gained correct ``think`` handling plus
    a thinking-channel filter on the streaming routes, so Qwen3-style
    reasoning arrives as typed ``message_type='thinking'`` chunks and is
    rendered as the separate thinking bubble — never as visible reply
    text.  Re-enabling thinking restores that intended separation.)
    """
    changed = _apply_chat_daemon(llm_settings)
    return changed


def _apply_chat_daemon(llm_settings: Any) -> bool:
    """Point *llm_settings* at the local chat daemon (ollama provider).

    Returns True when the settings changed from their prior state. When
    the pipeline is already ollama-routed (env-driven
    ``AIRUNNER_LLM_PROVIDER=ollama`` — the LAN/staging deployment style),
    this is a no-op: that routing is authoritative and already points at
    the configured chat daemon via ``AIRUNNER_OLLAMA_BASE_URL``.
    """
    if getattr(llm_settings, "use_ollama", False):
        # Already local (LAN/staging env-driven routing) — keep it.
        return False
    changed = False
    if getattr(llm_settings, "use_openrouter", False):
        llm_settings.use_openrouter = False
        changed = True
    if not getattr(llm_settings, "use_ollama", False):
        llm_settings.use_ollama = True
        changed = True
    if getattr(llm_settings, "use_local_llm", False):
        llm_settings.use_local_llm = False
        changed = True
    if getattr(llm_settings, "ollama_model", "") != CHAT_DAEMON_MODEL:
        llm_settings.ollama_model = CHAT_DAEMON_MODEL
        changed = True
    if getattr(llm_settings, "ollama_base_url", "") != CHAT_DAEMON_URL:
        llm_settings.ollama_base_url = CHAT_DAEMON_URL
        changed = True
    if changed:
        logger.info(
            "DIALOGUE routed to local chat daemon (%s, %s)",
            CHAT_DAEMON_URL, CHAT_DAEMON_MODEL,
        )
    return changed


__all__ = [
    "CHAT_DAEMON_MODEL",
    "CHAT_DAEMON_URL",
    "resolve_dialogue_llm_settings",
]
