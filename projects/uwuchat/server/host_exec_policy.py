"""Host-execution classification and policy for UwUchat code mode.

Decides whether a code-mode command should run in the sandboxed
headlesscode container (default, safe) or be delegated to the
host-executor agent (consent-gated, runs with the user's real git/gh
identity).  Also owns the per-user policy (groups, whitelist, blacklist,
enable_all) that the consent gate enforces.

See plans/uwuchat-host-executor-with-consent.md.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from airunner_services.database.models.user import User

logger = logging.getLogger(__name__)

# Hard-coded dangerous patterns — ALWAYS denied, even with enable_all.
# Kept in sync with scripts/host-executor.py's DEFAULT_BLACKLIST.
HARD_BLACKLIST: tuple[str, ...] = (
    r"rm\s+-rf\s+/",
    r"sudo\b",
    r"git\s+push\s+.*--force",
    r"shutdown|reboot|poweroff|halt\b",
    r"mkfs\.|fdisk|parted\b",
    r"chmod\s+777\s+/",
    r"curl\s+.*\|\s*(ba)?sh\b",
    r"dd\s+if=.*of=/dev/",
)

DEFAULT_GROUPS: dict[str, bool] = {
    "git": True,
    "gh": True,
    "shell": False,
    "file": True,
    "network": False,
    "other": False,
}

# Commands that MUST run on the host (need real identity / are mutating).
# Everything else runs in the container.
HOST_GROUP_PREFIXES: dict[str, tuple[str, ...]] = {
    "git": ("git push", "git commit", "git merge", "git rebase", "git tag"),
    "gh": ("gh issue create", "gh issue close", "gh issue edit",
           "gh pr create", "gh pr merge", "gh pr close", "gh release"),
    "shell": (),   # shell group defaults to container; host only via policy
    "network": (),  # network defaults to container; host only via policy
}

_GIT_CMDS = ("git",)
_GH_CMDS = ("gh",)
_NET_CMDS = ("curl", "wget", "scp", "rsync", "ssh", "ftp", "nc", "ncat")
_SHELL_CMDS = (
    "bash", "sh", "zsh", "python", "python3", "node", "npm", "npx",
    "yarn", "pnpm", "ruby", "perl", "make", "cmake", "cargo", "go",
    "docker", "podman", "systemctl", "service",
)


def classify_group(command: str) -> str:
    """Return the policy group a command belongs to."""
    first = command.strip().split(None, 1)[0].lower() if command.strip() else ""
    if first in _GIT_CMDS:
        return "git"
    if first in _GH_CMDS:
        return "gh"
    if first in _NET_CMDS:
        return "network"
    if first in _SHELL_CMDS:
        return "shell"
    return "other"


def needs_host(command: str) -> bool:
    """Return True when a command must run on the host.

    Container-safe commands (reads, tests, gh issue list) run in the
    sandbox.  Mutating git/gh operations (push, commit, merge, issue/pr
    writes) and anything the user's policy routes to the host run
    through the consent-gated host executor.
    """
    cmd = command.strip()
    if not cmd:
        return False
    if any(re.search(p, cmd, re.IGNORECASE) for p in HARD_BLACKLIST):
        return True  # dangerous — route to host so the gate can deny
    group = classify_group(cmd)
    for prefix in HOST_GROUP_PREFIXES.get(group, ()):
        if cmd.lower().startswith(prefix):
            return True
    return False


@dataclass
class HostExecPolicy:
    """Per-user host-executor policy (mirrors scripts/host-executor.py)."""

    enabled: bool = True
    enable_all: bool = False
    groups: dict[str, bool] = field(default_factory=lambda: dict(DEFAULT_GROUPS))
    whitelist: list[str] = field(default_factory=list)
    blacklist: list[str] = field(default_factory=list)
    allow_always: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        """Serialize to the JSON shape the host agent consumes."""
        return json.dumps({
            "enabled": self.enabled,
            "enable_all": self.enable_all,
            "groups": self.groups,
            "whitelist": self.whitelist,
            "blacklist": self.blacklist,
            "allow_always": self.allow_always,
        })

    @classmethod
    def from_user_data(cls, user: Any | None) -> "HostExecPolicy":
        """Build a policy from a User row's ``data.host_exec`` JSON."""
        policy = cls()
        if user is None:
            return policy
        raw = (user.data or {}).get("host_exec", {})
        if not isinstance(raw, dict):
            return policy
        if isinstance(raw.get("enabled"), bool):
            policy.enabled = raw["enabled"]
        if isinstance(raw.get("enable_all"), bool):
            policy.enable_all = raw["enable_all"]
        if isinstance(raw.get("groups"), dict):
            for key, value in raw["groups"].items():
                if key in policy.groups and isinstance(value, bool):
                    policy.groups[key] = value
        for key in ("whitelist", "blacklist", "allow_always"):
            if isinstance(raw.get(key), list):
                setattr(policy, key, [str(x) for x in raw[key] if str(x).strip()])
        return policy

    @classmethod
    def save_to_user(
        cls, user: Any, policy: "HostExecPolicy",
    ) -> None:
        """Persist a policy into a User row's ``data.host_exec``."""
        data = dict(user.data or {})
        data["host_exec"] = json.loads(policy.to_json())
        User.objects.update(user.id, data=data)


__all__ = [
    "DEFAULT_GROUPS",
    "HARD_BLACKLIST",
    "HostExecPolicy",
    "classify_group",
    "needs_host",
]
