"""Unit tests for the host-exec policy/classification module.

Covers needs_host (container vs host routing), classify_group, the
policy round-trip (from_user_data / save_to_user), and the default
policy shape.  All DB interactions are mocked.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from projects.uwuchat.server.host_exec_policy import (
    DEFAULT_GROUPS,
    HostExecPolicy,
    classify_group,
    needs_host,
)


def test_classify_group() -> None:
    """Command classification maps to the right group."""
    assert classify_group("git push") == "git"
    assert classify_group("gh issue list") == "gh"
    assert classify_group("curl http://x") == "network"
    assert classify_group("python3 x.py") == "shell"
    assert classify_group("custom-tool --x") == "other"


def test_needs_host_mutating_git() -> None:
    """Mutating git operations run on the host."""
    assert needs_host("git push origin main") is True
    assert needs_host("git commit -m x") is True
    assert needs_host("git status") is False
    assert needs_host("git log --oneline") is False


def test_needs_host_gh_read_vs_write() -> None:
    """gh reads stay in the container; gh writes go to the host."""
    assert needs_host("gh issue list --repo <your-org>/airunnerweb") is False
    assert needs_host("gh issue create --title x") is True
    assert needs_host("gh pr merge 12") is True


def test_needs_host_dangerous() -> None:
    """Dangerous commands route to the host so the gate can deny."""
    assert needs_host("rm -rf /") is True
    assert needs_host("sudo rm -rf /home") is True


def test_policy_defaults() -> None:
    """The default policy matches the expected groups."""
    policy = HostExecPolicy()
    assert policy.enabled is True
    assert policy.enable_all is False
    assert policy.groups == DEFAULT_GROUPS
    assert policy.whitelist == []
    assert policy.blacklist == []


def test_policy_from_user_data() -> None:
    """Policy loads from a user's data.host_exec."""
    user = SimpleNamespace(data={
        "host_exec": {
            "enabled": True,
            "enable_all": True,
            "groups": {"shell": True},
            "whitelist": ["gh issue list"],
            "blacklist": ["sudo"],
            "allow_always": [],
        },
    })
    policy = HostExecPolicy.from_user_data(user)
    assert policy.enable_all is True
    assert policy.groups["shell"] is True
    assert policy.whitelist == ["gh issue list"]
    assert policy.blacklist == ["sudo"]


def test_policy_from_user_data_missing() -> None:
    """A user without host_exec data gets the default policy."""
    user = SimpleNamespace(data={})
    policy = HostExecPolicy.from_user_data(user)
    assert policy.enable_all is False
    assert policy.groups == DEFAULT_GROUPS


def test_policy_save_to_user(monkeypatch: pytest.MonkeyPatch) -> None:
    """save_to_user persists the policy into data.host_exec."""
    from airunner_services.database.models.user import User

    updated = {}

    def fake_update(user_id: int, **kwargs) -> None:
        updated["id"] = user_id
        updated["data"] = kwargs["data"]

    monkeypatch.setattr(User.objects, "update", fake_update)
    policy = HostExecPolicy(enable_all=True)
    user = SimpleNamespace(id=42, data={})
    HostExecPolicy.save_to_user(user, policy)
    assert updated["id"] == 42
    stored = updated["data"]["host_exec"]
    assert stored["enable_all"] is True
