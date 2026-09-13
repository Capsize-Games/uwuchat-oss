"""SSH helper for running commands on the Hetzner server.

Reads SSH credentials from ``~/.config/airunner-deploy/config``
and ``~/.config/airunner-deploy/secrets`` (same files used by
``scripts/setup-github-runner.sh``).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


_CONFIG_DIR = Path.home() / ".config" / "airunner-deploy"


def _load_deploy_env() -> dict[str, str]:
    """Load HETZNER_HOST, HETZNER_USER, HETZNER_SSH_KEY from deploy
    config files."""
    env: dict[str, str] = {}
    for cfg_name in ("config", "secrets"):
        cfg_path = _CONFIG_DIR / cfg_name
        if not cfg_path.exists():
            continue
        for line in cfg_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("\"'")
            if key and value:
                env[key] = value
    return env


@dataclass(frozen=True)
class SSHResult:
    """Result of executing a command over SSH."""

    success: bool
    stdout: str
    stderr: str
    exit_code: int
    command: str
    host: str

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "stdout": self.stdout[-4000:],
            "stderr": self.stderr[-2000:],
            "exit_code": self.exit_code,
            "command": self.command,
            "host": self.host,
        }


def _ssh_args() -> list[str]:
    """Build SSH argument list from deploy config."""
    env = _load_deploy_env()
    host = env.get("HETZNER_HOST")
    user = env.get("HETZNER_USER", "root")
    key = env.get("HETZNER_SSH_KEY", "")
    if not host:
        raise RuntimeError(
            "HETZNER_HOST not configured in "
            "~/.config/airunner-deploy/config"
        )
    key_path = Path(key).expanduser()
    if not key_path.exists():
        raise RuntimeError(f"SSH key not found: {key_path}")
    return [
        "ssh",
        "-i",
        str(key_path),
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ConnectTimeout=15",
        f"{user}@{host}",
    ]


def run_ssh_command(command: str) -> SSHResult:
    """Run a command on the Hetzner server via SSH.

    Args:
        command: Shell command to execute.

    Returns:
        ``SSHResult`` with success, output, and exit code.
    """
    env = _load_deploy_env()
    host = env.get("HETZNER_HOST", "unknown")
    args = _ssh_args() + [command]
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=120,
        )
        return SSHResult(
            success=proc.returncode == 0,
            stdout=proc.stdout.strip(),
            stderr=proc.stderr.strip(),
            exit_code=proc.returncode,
            command=command,
            host=host,
        )
    except FileNotFoundError:
        return SSHResult(
            success=False,
            stdout="",
            stderr="SSH client not installed on this server",
            exit_code=-1,
            command=command,
            host=host,
        )
    except subprocess.TimeoutExpired:
        return SSHResult(
            success=False,
            stdout="",
            stderr="SSH command timed out after 120 seconds",
            exit_code=-1,
            command=command,
            host=host,
        )
    except Exception as exc:
        return SSHResult(
            success=False,
            stdout="",
            stderr=str(exc),
            exit_code=-1,
            command=command,
            host=host,
        )
