import { useEffect, useState, useCallback } from "react";
import { useAuth } from "./useAuth";

export interface QuotaState {
  turnsUsed: number;
  turnsUsedToday: number;
  turnsCap: number | null;
  dailyCap: number | null;
  pct: number;
  pctToday: number;
  periodEnd: string | null;
  periodDaysRemaining: number | null;
  tier: string | null;
  isUnlimited: boolean;
  loading: boolean;
  error: string | null;
}

const DEFAULT: QuotaState = {
  turnsUsed: 0,
  turnsUsedToday: 0,
  turnsCap: null,
  dailyCap: null,
  pct: 0,
  pctToday: 0,
  periodEnd: null,
  periodDaysRemaining: null,
  tier: null,
  isUnlimited: false,
  loading: true,
  error: null,
};

export function useQuota(
  previewTier?: string,
): QuotaState & { refresh: () => void } {
  const { accessToken } = useAuth();
  const [state, setState] = useState<QuotaState>(DEFAULT);

  const refresh = useCallback(async () => {
    if (!accessToken) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const url = previewTier
        ? `/api/v1/usage/quota?preview_tier=${previewTier}`
        : "/api/v1/usage/quota";
      const res = await fetch(url, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setState({
        turnsUsed: data.turns_used,
        turnsUsedToday: data.turns_used_today,
        turnsCap: data.turns_cap,
        dailyCap: data.daily_cap,
        pct: data.pct,
        pctToday: data.pct_today,
        periodEnd: data.period_end,
        periodDaysRemaining: data.period_days_remaining ?? null,
        tier: data.tier,
        isUnlimited: data.is_unlimited,
        loading: false,
        error: null,
      });
    } catch (e) {
      setState((s) => ({
        ...s,
        loading: false,
        error:
          e instanceof Error
            ? e.message
            : "Failed to load quota",
      }));
    }
  }, [accessToken, previewTier]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { ...state, refresh };
}
