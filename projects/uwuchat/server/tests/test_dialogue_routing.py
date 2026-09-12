"""Unit tests for the per-conversation DIALOGUE routing (Decision B).

Chat and code models are independent: the chat model never depends on
the conversation's code-mode state. The resolver points the static cloud
default at the local chat daemon, and is a no-op when the pipeline is
already ollama-routed (the LAN/staging env-driven deployment style). The
framework mixin and the project resolver are tested separately: the
resolver here asserts the right provider/model gets chosen; the mixin
tests assert the guarded import + settings-mutation wiring.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from projects.uwuchat.server import dialogue_routing as mod


def _llm_settings(**overrides) -> SimpleNamespace:
    """Return a fake llm_settings object with cloud defaults."""
    defaults = {
        "use_openrouter": True,
        "use_ollama": False,
        "use_local_llm": False,
        "model": "deepseek/deepseek-v4-flash-0731",
        "ollama_model": "",
        "ollama_base_url": "http://localhost:11434",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_cloud_default_routes_to_chat_daemon() -> None:
    """A cloud-routed pipeline is pointed at the local chat daemon.

    Chat is independent of code mode — this must hold regardless of the
    conversation's code-mode state.
    """
    settings = _llm_settings()
    changed = mod.resolve_dialogue_llm_settings(settings, 42)

    assert changed is True
    assert settings.use_ollama is True
    assert settings.use_openrouter is False
    assert settings.ollama_model == mod.CHAT_DAEMON_MODEL
    assert settings.ollama_base_url == mod.CHAT_DAEMON_URL


def test_routes_to_chat_daemon_without_conversation_id() -> None:
    """A missing conversation id still routes to the chat daemon."""
    settings = _llm_settings()
    changed = mod.resolve_dialogue_llm_settings(settings, None)

    assert changed is True
    assert settings.use_ollama is True
    assert settings.ollama_base_url == mod.CHAT_DAEMON_URL


def test_routes_to_chat_daemon_when_code_mode_lookup_fails() -> None:
    """A code-mode lookup failure must not affect chat routing.

    Chat no longer queries code mode at all, so a DB failure cannot
    change the outcome.
    """
    settings = _llm_settings()
    with patch(
        "projects.uwuchat.server.code_mode_service.get_code_mode",
        side_effect=RuntimeError("db down"),
    ):
        changed = mod.resolve_dialogue_llm_settings(settings, 42)

    assert changed is True
    assert settings.use_ollama is True
    assert settings.ollama_base_url == mod.CHAT_DAEMON_URL


def test_ollama_routed_pipeline_is_noop() -> None:
    """An already-ollama-routed pipeline (LAN/staging env-driven) is kept.

    ``AIRUNNER_LLM_PROVIDER=ollama`` is authoritative — the hook must not
    fight it or substitute an unreachable container-name URL.
    """
    settings = _llm_settings(
        use_openrouter=False,
        use_ollama=True,
        ollama_model="qwen3-14b",
        ollama_base_url="http://192.168.1.100:11435",
    )
    changed = mod.resolve_dialogue_llm_settings(settings, 42)

    assert changed is False
    assert settings.use_ollama is True
    assert settings.use_openrouter is False
    assert settings.ollama_model == "qwen3-14b"
    assert settings.ollama_base_url == "http://192.168.1.100:11435"


def test_routes_to_chat_daemon_after_cloud() -> None:
    """Switching from a prior local state to a cloud state re-routes."""
    settings = _llm_settings(
        use_openrouter=False,
        use_ollama=True,
        ollama_model="qwen3.5-9b:latest",
        ollama_base_url="http://lan-daemon-daemon-1:11434",
    )
    settings.use_ollama = False
    settings.use_openrouter = True
    settings.ollama_model = ""
    settings.ollama_base_url = ""
    changed = mod.resolve_dialogue_llm_settings(settings, 42)

    assert changed is True
    assert settings.use_ollama is True
    assert settings.use_openrouter is False


def test_local_chat_keeps_thinking_on_request() -> None:
    """Routing to the local chat daemon leaves thinking enabled.

    The daemon's ollama-compat layer now handles ``think=true``
    correctly (separate reasoning channel + thinking filter on the
    streaming routes), so Qwen3-style reasoning arrives as typed
    ``thinking`` chunks — never as visible reply text.
    """
    settings = _llm_settings()
    request = SimpleNamespace(enable_thinking=True)
    changed = mod.resolve_dialogue_llm_settings(settings, 42, request)

    assert changed is True
    assert request.enable_thinking is True


def test_ollama_routed_pipeline_keeps_thinking() -> None:
    """An already-ollama-routed pipeline at a REMOTE daemon keeps thinking.

    The env-driven chat daemon at a remote address is a full pipeline
    path, not the local dev daemon with the think=true bug — don't
    disable thinking for it.
    """
    settings = _llm_settings(
        use_openrouter=False,
        use_ollama=True,
        ollama_model="qwen3-14b",
        ollama_base_url="http://192.168.1.100:11435",
    )
    request = SimpleNamespace(enable_thinking=True)
    changed = mod.resolve_dialogue_llm_settings(settings, 42, request)

    assert changed is False
    assert request.enable_thinking is True


def test_env_routed_dev_chat_daemon_keeps_thinking() -> None:
    """Env-driven routing to the local dev chat daemon keeps thinking.

    ``AIRUNNER_LLM_PROVIDER=ollama`` with the dev daemon URL/model
    (the local-dev style) is a no-op for the resolver (changed=False),
    and thinking is left enabled — the daemon handles it correctly.
    """
    settings = _llm_settings(
        use_openrouter=False,
        use_ollama=True,
        ollama_model=mod.CHAT_DAEMON_MODEL,
        ollama_base_url=mod.CHAT_DAEMON_URL,
    )
    request = SimpleNamespace(enable_thinking=True)
    changed = mod.resolve_dialogue_llm_settings(settings, 42, request)

    assert changed is False
    assert request.enable_thinking is True


# ---------------------------------------------------------------------------
# Framework mixin — guarded import + settings mutation wiring
# ---------------------------------------------------------------------------


_MIXIN_MOD = (
    "airunner_services.llm.managers.mixins.request_handling_mixin"
    "._dialogue_routing"
)


def _patch_project(project: str):
    """Point the mixin's project lookup at *project* and stub the module
    import so no real project module is loaded."""
    import airunner_services.llm.managers.mixins.request_handling_mixin \
        ._dialogue_routing as dr_mod

    return patch.object(
        dr_mod.os.environ, "get",
        side_effect=lambda k, d="": project if k == "AIRUNNER_PROJECT" else d,
    ), patch.object(
        dr_mod.importlib, "import_module",
        return_value=MagicMock(resolve_dialogue_llm_settings=lambda s, c: True),
    )


def test_mixin_resolver_imports_project_module() -> None:
    """The mixin's resolver imports the active project's module."""
    from airunner_services.llm.managers.mixins.request_handling_mixin import (
        RequestHandlingMixin,
    )

    with patch(
        f"{_MIXIN_MOD}.os.environ.get",
        return_value="uwuchat",
    ), patch(
        f"{_MIXIN_MOD}.importlib.import_module",
        return_value=MagicMock(resolve_dialogue_llm_settings=lambda s, c: True),
    ):
        resolver = RequestHandlingMixin._dialogue_routing_resolver()
    assert callable(resolver)


def test_mixin_returns_false_without_project_module() -> None:
    """No project module → the hook is a no-op (returns False)."""
    from airunner_services.llm.managers.mixins.request_handling_mixin \
        ._dialogue_routing import RequestDialogueRoutingMixin

    owner = RequestDialogueRoutingMixin()
    owner.logger = MagicMock()
    owner.llm_settings = _llm_settings()
    with patch(
        f"{_MIXIN_MOD}.importlib.import_module",
        side_effect=ImportError("no project dialogue_routing module"),
    ):
        changed = owner._apply_dialogue_conversation_routing(None)

    assert changed is False


def test_mixin_mutates_settings_when_resolver_changes_them() -> None:
    """The mixin applies the resolver's mutation and reports True."""
    from airunner_services.llm.managers.mixins.request_handling_mixin \
        ._dialogue_routing import RequestDialogueRoutingMixin

    owner = RequestDialogueRoutingMixin()
    owner.logger = MagicMock()
    owner.llm_settings = _llm_settings()

    def _fake_resolve(settings, conversation_id, llm_request=None):
        settings.use_ollama = True
        settings.ollama_base_url = mod.CHAT_DAEMON_URL
        return True

    with patch(
        f"{_MIXIN_MOD}.os.environ.get",
        return_value="uwuchat",
    ), patch(
        f"{_MIXIN_MOD}.importlib.import_module",
        return_value=MagicMock(
            resolve_dialogue_llm_settings=_fake_resolve
        ),
    ):
        changed = owner._apply_dialogue_conversation_routing(42)

    assert changed is True
    assert owner.llm_settings.use_ollama is True
    assert owner.llm_settings.ollama_base_url == mod.CHAT_DAEMON_URL
