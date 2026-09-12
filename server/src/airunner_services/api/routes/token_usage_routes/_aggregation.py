"""Aggregation helpers for token usage admin views."""

from __future__ import annotations


def _tier_breakdown(
    rows: list, pipeline_key: str
) -> list[dict]:
    """Build tier-breakdown for DIALOGUE rows."""
    tier_groups: dict = {}
    for row in rows:
        if getattr(row, "pipeline_key", "") != pipeline_key:
            continue
        tier = getattr(row, "tier_name", None) or "unknown"
        if tier not in tier_groups:
            tier_groups[tier] = {
                "call_count": 0,
                "priced_count": 0,
                "cost": 0.0,
            }
        tier_groups[tier]["call_count"] += 1
        cost = getattr(row, "cost_usd", None)
        if cost is not None:
            tier_groups[tier]["priced_count"] += 1
            tier_groups[tier]["cost"] += float(cost)
    return [
        {
            "tier": t,
            "call_count": g["call_count"],
            "avg_cost_usd": round(
                g["cost"] / max(g["priced_count"], 1), 8
            ),
        }
        for t, g in sorted(tier_groups.items())
    ]


def _per_account_request_stats(rows: list) -> list[dict]:
    """Group *rows* by account_id, then by call_chain_id (one request).

    Returns one entry per account: total requests seen, how many of
    those had complete pricing, and cost stats computed only from the
    fully-priced ones.
    """
    by_account: dict[int, dict] = {}
    for row in rows:
        acct = int(row.account_id)
        chains = by_account.setdefault(acct, {})
        chains.setdefault(row.call_chain_id, []).append(row)

    account_ids = sorted(by_account.keys())
    emails = {
        a["account_id"]: a["email"]
        for a in _accounts_with_email(account_ids)
    }

    result = []
    for acct, chains in by_account.items():
        priced_costs = [
            sum(float(r.cost_usd) for r in chain_rows)
            for chain_rows in chains.values()
            if all(r.cost_usd is not None for r in chain_rows)
        ]
        total_cost = sum(priced_costs)
        priced_requests = len(priced_costs)
        result.append(
            {
                "account_id": acct,
                "email": emails.get(acct),
                "total_requests": len(chains),
                "priced_requests": priced_requests,
                "total_cost_usd": round(total_cost, 8),
                "avg_cost_per_request_usd": (
                    round(total_cost / priced_requests, 8)
                    if priced_requests
                    else None
                ),
            }
        )
    result.sort(key=lambda a: a["total_requests"], reverse=True)
    return result


def _accounts_with_email(account_ids: list[int]) -> list[dict]:
    """Return [{account_id, email}] for *account_ids*, email best-effort."""
    if not account_ids:
        return []
    try:
        from extensions.auth.server.models import Account

        rows = (
            Account.objects.query()
            .filter(Account.id.in_(account_ids))
            .all()
        )
        emails = {int(a.id): a.email for a in rows}
    except Exception:
        emails = {}
    return [
        {"account_id": aid, "email": emails.get(aid)}
        for aid in account_ids
    ]
