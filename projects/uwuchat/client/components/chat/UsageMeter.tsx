import { useQuota } from "../../hooks/useQuota";

interface UsageMeterProps {
  previewTier?: string;
  onRefreshRef?: React.MutableRefObject<(() => void) | null>;
}

export function UsageMeter({
  previewTier, onRefreshRef,
}: UsageMeterProps) {
  const quota = useQuota(previewTier);

  if (onRefreshRef) onRefreshRef.current = quota.refresh;

  if (quota.loading && quota.turnsUsed === 0) return null;
  if (quota.isUnlimited && !previewTier) {
    return (
      <div className="usage-meter usage-meter--admin">
        Admin &middot; unlimited messages
      </div>
    );
  }
  if (!quota.turnsCap) return null;

  const pct = quota.pct;
  const isWarning = pct >= 80 && pct < 100;
  const isExhausted = pct >= 100;

  const cls = [
    "usage-meter",
    isWarning && "usage-meter--warning",
    isExhausted && "usage-meter--exhausted",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={cls}>
      <div className="usage-meter__bar-track">
        <div
          className="usage-meter__bar-fill"
          // eslint-disable-next-line no-restricted-syntax -- computed dimension from state/prop
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
      <div className="usage-meter__label">
        {isExhausted
          ? (
            <>
              Message limit reached &middot;{" "}
              <a href="/subscribe" className="usage-meter__upgrade">
                Upgrade
              </a>
            </>
          )
          : (
            `${quota.turnsUsed} / ${quota.turnsCap} messages · ${Math.round(pct)}% used`
          )}
      </div>
    </div>
  );
}
