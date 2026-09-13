"""Poll headlesscode usage files and debit real cost per session.

Reads ``<workspace_root>/.headlesscode/usage/<session_id>.jsonl`` (the
finalized record — authoritative) or ``<session_id>.live.json`` (the
in-flight snapshot) with the same loose validation as headlesscode's
own ``readUsageFile``/``readLiveUsageFile``, then debits only the delta
since the last known cost for the session (the sum of prior
``session_debit`` ledger rows). Missing or malformed files are skipped,
never fatal.

Also exposes a small CLI entry point so the reconciler is testable and
admin-triggerable before any session-launch code exists.
"""

from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path

from projects.uwuchat.server.code_credits_service import (
    debit_session_delta,
    remaining_budget_usd,
    session_debits_total,
)


def _read_jsonl(path: Path) -> list[dict]:
    """Loose-validate one usage JSONL file.

    Mirrors headlesscode's ``readUsageFile``: a missing file yields
    ``[]`` and malformed/partial lines are skipped, never fatal.
    """
    if not path.exists():
        return []
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []
    records = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except ValueError:
            continue
        if (
            isinstance(parsed, dict)
            and isinstance(parsed.get("sessionId"), str)
            and isinstance(parsed.get("status"), str)
        ):
            records.append(parsed)
    return records


def _read_live(path: Path) -> dict | None:
    """Loose-validate one live snapshot (``*.live.json``).

    Mirrors headlesscode's ``readLiveUsageFile``: missing or malformed
    files yield ``None``.
    """
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        parsed = json.loads(raw)
    except ValueError:
        return None
    if (
        isinstance(parsed, dict)
        and isinstance(parsed.get("sessionId"), str)
        and parsed.get("status") == "running"
    ):
        return parsed
    return None


def _record_cost(record: dict, session_id: str) -> Decimal | None:
    """Return a record's ``costUsd`` as Decimal, or None when unusable."""
    if record.get("sessionId") != session_id:
        return None
    cost = record.get("costUsd")
    if not isinstance(cost, (int, float)):
        return None
    return Decimal(str(cost))


def _current_cost(
    jsonl_path: Path, live_path: Path, session_id: str
) -> Decimal | None:
    """Authoritative cost so far for one session, or None for no data.

    The finalized ``.jsonl`` record wins over a stale ``.live.json``
    snapshot when both exist (headlesscode's own documented precedence).
    """
    for record in reversed(_read_jsonl(jsonl_path)):
        cost = _record_cost(record, session_id)
        if cost is not None:
            return cost
    live = _read_live(live_path)
    if live is not None:
        cost = _record_cost(live, session_id)
        if cost is not None:
            return cost
    return None


def reconcile_session_usage(
    account_id: int, workspace_root: str, session_id: str
) -> Decimal:
    """Read a session's usage files and debit the cost delta.

    Returns the current remaining balance (clamped >= 0). Missing or
    malformed files leave the balance unchanged rather than erroring.
    """
    usage_dir = Path(workspace_root) / ".headlesscode" / "usage"
    cost = _current_cost(
        usage_dir / f"{session_id}.jsonl",
        usage_dir / f"{session_id}.live.json",
        session_id,
    )
    if cost is None:
        return remaining_budget_usd(account_id)
    prior = session_debits_total(account_id, session_id)
    delta = cost - prior
    if delta > 0:
        debit_session_delta(
            account_id,
            session_id,
            delta,
            note=f"reconciled session {session_id}",
        )
    return remaining_budget_usd(account_id)


def main(argv: list[str] | None = None) -> int:
    """CLI: reconcile one session's usage, print the remaining balance."""
    parser = argparse.ArgumentParser(
        description="Debit a headlesscode session's usage cost."
    )
    parser.add_argument("account_id", type=int)
    parser.add_argument("workspace_root")
    parser.add_argument("session_id")
    args = parser.parse_args(argv)
    balance = reconcile_session_usage(
        args.account_id, args.workspace_root, args.session_id
    )
    print(balance)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
