"""Turn quota service for UwUchat subscriptions.

Tier data comes from the active
:class:`airunner_services.billing.BillingProvider`, never from a
billing vendor module directly.  With the shipped
``UnlimitedBillingProvider`` this service reports unlimited access for
every account; a deployment that sells subscriptions installs a
provider (see ``airunner_services.billing``).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import TypedDict

from sqlalchemy import distinct, func, select

from airunner_services.billing import TierLimits, get_billing_provider
from airunner_services.database.session import public_session_scope
from airunner_services.database.models.pipeline_token_usage import (
    PipelineTokenUsage,
)
from extensions.auth.server.models import Account


class QuotaResult(TypedDict):
    turns_used: int
    turns_used_today: int
    turns_cap: int | None
    daily_cap: int | None
    pct: float
    pct_today: float
    period_start: str
    period_end: str | None
    period_days_remaining: int | None
    tier: str | None
    is_unlimited: bool
    has_access: bool


def _utcnow() -> datetime:
    """Return the current UTC time (naive, matching the DB columns)."""
    return datetime.utcnow()


def _load_account(account_id: int) -> tuple[bool, str]:
    """Return ``(is_superuser, tenant_key)`` for *account_id*."""
    with public_session_scope() as session:
        acct: Account | None = session.get(Account, account_id)
        if acct is None:
            raise ValueError(f"Account {account_id} not found")
        return bool(acct.is_superuser), acct.tenant_schema


def _resolve_billing(
    account_id: int,
    is_superuser: bool,
    preview_tier: str | None,
) -> tuple[str | None, TierLimits, datetime | None]:
    """Return ``(tier, limits, period_end)`` for one account.

    *preview_tier* — superuser only; forces that tier's caps instead of
    the account's real tier (usage counts remain real).
    """
    provider = get_billing_provider()
    period_end = provider.get_period_end(account_id)
    if is_superuser and preview_tier:
        return preview_tier, provider.get_tier_limits(preview_tier), period_end
    tier = provider.get_subscription_tier(account_id)
    if is_superuser:
        return tier, TierLimits(), period_end
    return tier, provider.get_tier_limits(tier), period_end


def _period_start(period_end: datetime | None, period_days: int) -> datetime:
    """Return the start of the account's current quota period."""
    if period_end:
        return period_end - timedelta(days=period_days)
    now = _utcnow()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _count_turns_after(session, tenant_key: str, after: datetime) -> int:
    """Count distinct call chains recorded for a tenant after *after*."""
    result = session.execute(
        select(
            func.count(distinct(PipelineTokenUsage.call_chain_id))
        ).where(
            PipelineTokenUsage.tenant_key == tenant_key,
            PipelineTokenUsage.recorded_at >= after,
            PipelineTokenUsage.skipped.is_(False),
            PipelineTokenUsage.call_chain_id.isnot(None),
        )
    )
    return result.scalar_one() or 0


def _count_turns(tenant_key: str, period_start: datetime) -> tuple[int, int]:
    """Return ``(turns_used, turns_used_today)`` for one tenant."""
    today_start = _utcnow().replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    with public_session_scope() as session:
        return (
            _count_turns_after(session, tenant_key, period_start),
            _count_turns_after(session, tenant_key, today_start),
        )


def _sum_tokens_today(tenant_key: str) -> int:
    """Return the tenant's input + output tokens for the current UTC day."""
    today_start = _utcnow().replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    with public_session_scope() as session:
        result = session.execute(
            select(
                func.sum(
                    PipelineTokenUsage.input_tokens
                    + PipelineTokenUsage.output_tokens
                )
            ).where(
                PipelineTokenUsage.tenant_key == tenant_key,
                PipelineTokenUsage.recorded_at >= today_start,
                PipelineTokenUsage.skipped.is_(False),
            )
        )
        return result.scalar_one() or 0


def _pct(used: int, cap: int | None) -> float:
    """Return usage as a percentage of *cap*, capped at 100."""
    if not cap:
        return 0.0
    return min(used / cap * 100, 100.0)


def get_quota(
    account_id: int,
    *,
    preview_tier: str | None = None,
) -> QuotaResult:
    """Return quota state for account_id.

    preview_tier — superuser only; if set, returns caps for that tier
    instead of the account's real tier (usage counts remain real).
    """
    is_superuser, tenant_key = _load_account(account_id)
    tier, limits, period_end = _resolve_billing(
        account_id, is_superuser, preview_tier
    )
    is_unlimited = limits.is_unlimited
    period_start = _period_start(period_end, limits.period_days)
    turns_used, turns_used_today = _count_turns(tenant_key, period_start)

    turns_cap = None if is_unlimited else limits.turns_cap
    daily_cap = None if is_unlimited else limits.daily_cap
    days_remaining: int | None = None
    if period_end:
        days_remaining = (period_end - _utcnow()).days

    return QuotaResult(
        turns_used=turns_used,
        turns_used_today=turns_used_today,
        turns_cap=turns_cap,
        daily_cap=daily_cap,
        pct=round(_pct(turns_used, turns_cap), 1),
        pct_today=round(_pct(turns_used_today, daily_cap), 1),
        period_start=period_start.isoformat(),
        period_end=period_end.isoformat() if period_end else None,
        period_days_remaining=days_remaining,
        tier=tier,
        is_unlimited=is_unlimited,
        has_access=limits.has_access,
    )


def is_over_quota(
    account_id: int, *, grace_pct: float = 110.0
) -> bool:
    """Return True if account has exceeded its monthly or daily cap.

    By default, blocks at 110 % of the cap (10 % grace buffer).
    Pass 100.0 for a hard stop.

    Accounts the active provider reports as having no access (no active
    subscription) are always over quota.  A provider that grants
    unlimited access never blocks.
    """
    q = get_quota(account_id)
    if q["is_unlimited"]:
        return False
    if not q["has_access"]:
        return True
    cap = q["turns_cap"] or 0
    daily = q["daily_cap"] or 0
    if cap and q["turns_used"] >= int(cap * grace_pct / 100):
        return True
    if daily and q["turns_used_today"] >= int(daily * grace_pct / 100):
        return True
    return False


def is_over_daily_token_limit(account_id: int) -> bool:
    """Return True if *account_id* has exceeded its daily token ceiling.

    Sums ``input_tokens + output_tokens`` from ``PipelineTokenUsage``
    for the current UTC day and compares against the daily token cap
    the active billing provider reports for the account's tier.
    Superusers are exempt.
    """
    try:
        is_superuser, tenant_key = _load_account(account_id)
        if is_superuser:
            return False
        provider = get_billing_provider()
        tier = provider.get_subscription_tier(account_id)
        limits = provider.get_tier_limits(tier)
        if not limits.has_access:
            return True
        cap = limits.daily_token_cap
        if not cap:
            return False
        total = _sum_tokens_today(tenant_key)
    except Exception:
        import logging

        _log = logging.getLogger(__name__)
        _log.exception(
            "Daily token limit check failed for account %d — "
            "failing closed (blocking spend)",
            account_id,
        )
        return True
    return total >= cap
