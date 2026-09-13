"""Unit tests for the GPU inference-mode switcher.

Mocks the docker/HTTP layer (``daemon_docker_client`` and
``gpu_inference_mode.daemon_ready``) — no real docker socket, no real
daemons. Follows the codebase's established
``unittest.mock.patch``-on-the-specific-function pattern.

Chat and code models are independently configurable. When they share the
SAME daemon container (the dev default — Qwen3-14B for both), the switch
no-ops. When they differ, the switch stops one daemon and starts the
other.
"""

from __future__ import annotations

from unittest.mock import patch

import projects.uwuchat.server.gpu_inference_mode as mod


def _patch_docker(chat_state="running", code_state="running"):
    """Patch the docker client to report fixed container states."""
    return patch(
        "projects.uwuchat.server.daemon_docker_client.container_state",
        side_effect=lambda c: (
            chat_state if c == mod.CHAT_DAEMON_CONTAINER else code_state
        ),
    )


def test_same_daemon_detected() -> None:
    """_same_daemon is True when both container names are equal."""
    with patch.object(
        mod, "CHAT_DAEMON_CONTAINER", "code-daemon-daemon-1"
    ), patch.object(
        mod, "CODE_DAEMON_CONTAINER", "code-daemon-daemon-1"
    ):
        assert mod._same_daemon() is True


def test_same_daemon_switch_is_noop() -> None:
    """Chat and code sharing one daemon → apply_code_mode does nothing.

    Toggling code mode must NOT stop the single container both modes
    depend on. No docker calls at all, and the state is reported reached.
    """
    with patch.object(
        mod, "CHAT_DAEMON_CONTAINER", "code-daemon-daemon-1"
    ), patch.object(
        mod, "CODE_DAEMON_CONTAINER", "code-daemon-daemon-1"
    ), patch(
        "projects.uwuchat.server.daemon_docker_client.container_state",
    ) as container_state, patch(
        "projects.uwuchat.server.gpu_inference_mode._start_container",
    ) as start, patch(
        "projects.uwuchat.server.gpu_inference_mode._stop_container",
    ) as stop, patch(
        "projects.uwuchat.server.gpu_inference_mode._wait_for_daemon",
    ) as wait:
        assert mod.apply_code_mode(True) is True
        assert mod.apply_code_mode(False) is True

    container_state.assert_not_called()
    start.assert_not_called()
    stop.assert_not_called()
    wait.assert_not_called()


def test_code_mode_on_stops_chat_starts_code() -> None:
    """Code mode ON (separate daemons) stops chat and starts code."""
    from contextlib import ExitStack

    with ExitStack() as stack:
        stack.enter_context(_patch_docker(
            chat_state="running", code_state="exited"
        ))
        start = stack.enter_context(patch(
            "projects.uwuchat.server.gpu_inference_mode._start_container",
            return_value=True,
        ))
        stop = stack.enter_context(patch(
            "projects.uwuchat.server.gpu_inference_mode._stop_container",
            return_value=True,
        ))
        wait = stack.enter_context(patch(
            "projects.uwuchat.server.gpu_inference_mode._wait_for_daemon",
            return_value=True,
        ))
        ok = mod.apply_code_mode(True)

    assert ok is True
    stop.assert_called_once_with(mod.CHAT_DAEMON_CONTAINER)
    start.assert_called_once_with(mod.CODE_DAEMON_CONTAINER)
    wait.assert_called_once_with(mod.CODE_DAEMON_CONTAINER)


def test_code_mode_off_stops_code_starts_chat() -> None:
    """Code mode OFF (separate daemons) stops code and starts chat."""
    from contextlib import ExitStack

    with ExitStack() as stack:
        stack.enter_context(_patch_docker(
            chat_state="exited", code_state="running"
        ))
        start = stack.enter_context(patch(
            "projects.uwuchat.server.gpu_inference_mode._start_container",
            return_value=True,
        ))
        stop = stack.enter_context(patch(
            "projects.uwuchat.server.gpu_inference_mode._stop_container",
            return_value=True,
        ))
        wait = stack.enter_context(patch(
            "projects.uwuchat.server.gpu_inference_mode._wait_for_daemon",
            return_value=True,
        ))
        ok = mod.apply_code_mode(False)

    assert ok is True
    stop.assert_called_once_with(mod.CODE_DAEMON_CONTAINER)
    start.assert_called_once_with(mod.CHAT_DAEMON_CONTAINER)
    wait.assert_called_once_with(mod.CHAT_DAEMON_CONTAINER)


def test_code_mode_on_fails_when_code_start_fails() -> None:
    """A failed code-daemon start makes apply_code_mode return False."""
    with _patch_docker(chat_state="running", code_state="exited"), patch(
        "projects.uwuchat.server.gpu_inference_mode._start_container",
        return_value=False,
    ), patch(
        "projects.uwuchat.server.gpu_inference_mode._stop_container",
        return_value=True,
    ), patch(
        "projects.uwuchat.server.gpu_inference_mode._wait_for_daemon",
        return_value=True,
    ):
        ok = mod.apply_code_mode(True)

    assert ok is False


def test_code_mode_off_fails_when_daemon_not_ready() -> None:
    """A chat daemon that never becomes ready makes the switch fail."""
    with _patch_docker(chat_state="exited", code_state="running"), patch(
        "projects.uwuchat.server.gpu_inference_mode._start_container",
        return_value=True,
    ), patch(
        "projects.uwuchat.server.gpu_inference_mode._stop_container",
        return_value=True,
    ), patch(
        "projects.uwuchat.server.gpu_inference_mode._wait_for_daemon",
        return_value=False,
    ):
        ok = mod.apply_code_mode(False)

    assert ok is False


def test_apply_code_mode_never_raises_on_docker_error() -> None:
    """A docker API exception is swallowed; the switch reports failure."""
    with patch(
        "projects.uwuchat.server.daemon_docker_client.container_state",
        side_effect=RuntimeError("socket gone"),
    ), patch(
        "projects.uwuchat.server.gpu_inference_mode._start_container",
        return_value=False,
    ), patch(
        "projects.uwuchat.server.gpu_inference_mode._stop_container",
        return_value=False,
    ):
        # Must not raise despite the docker errors.
        ok = mod.apply_code_mode(True)

    assert ok is False
