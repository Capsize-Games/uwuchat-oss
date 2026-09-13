import type { QuotaState } from "../../hooks/useQuota";
import styles from "./UsageBar.module.css";

interface UsageBarProps {
  quota: QuotaState;
  compact?: boolean;
}

export function UsageBar({ quota, compact = false }: UsageBarProps) {
  if (quota.loading && quota.turnsUsed === 0) return null;
  if (quota.isUnlimited) return null;
  if (!quota.turnsCap) return null;

  const pct = Math.min(quota.pct, 100);
  const daysLeft = quota.periodDaysRemaining;
  const expired = daysLeft !== null && daysLeft < 0;
  const danger = pct >= 95 || expired;
  const warn = pct >= 75 && pct < 95 && !expired;

  const accent = danger
    ? "rgba(239,68,68,0.90)" : warn ? "rgba(251,191,36,0.85)" : "rgba(148,163,184,0.55)";
  const bg = danger
    ? "rgba(239,68,68,0.12)" : warn ? "rgba(251,191,36,0.10)" : "rgba(148,163,184,0.06)";
  const barBg = danger
    ? "rgba(239,68,68,0.20)" : warn ? "rgba(251,191,36,0.18)" : "rgba(148,163,184,0.10)";

  const daysLabel =
    daysLeft === null ? ""
    : daysLeft < 0 ? "· Expired"
    : daysLeft === 0 ? "· Last day"
    : `· ${daysLeft}d left`;

  return (
    <div
      className={styles.bar}
      // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
      style={{
        background: bg,
        borderTop: `1px solid ${danger ? "rgba(239,68,68,0.18)" : "rgba(255,255,255,0.05)"}`,
        borderLeft: `1px solid ${danger ? "rgba(239,68,68,0.18)" : "rgba(255,255,255,0.05)"}`,
        borderRight: `1px solid ${danger ? "rgba(239,68,68,0.18)" : "rgba(255,255,255,0.05)"}`,
        color: accent,
      }}
    >
      <div className={styles.left}>
        <span className={styles.msgCount}>
          <span className={styles.msgCountBold}>{quota.turnsUsed}</span>
          <span className={styles.msgCountMuted}> / {quota.turnsCap}</span>
        </span>
        {/* eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation */}
        <div className={styles.track} style={{ background: barBg }}>
          {/* eslint-disable-next-line no-restricted-syntax -- computed dimension from state/prop */}
          <div className={styles.fill} style={{ width: `${pct}%`, background: accent }} />
        </div>
        <span className={styles.pct}>{Math.round(pct)}%</span>
      </div>
      <div className={styles.right}>
        {daysLabel && (
          <span
            className={styles.daysLabel}
            // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
            style={{ opacity: daysLeft === 0 ? 1 : 0.65, fontWeight: daysLeft === 0 ? 600 : 400 }}
          >
            {daysLabel}
          </span>
        )}
        {danger && <span className={styles.upgradeLink}>Limit reached</span>}
      </div>
    </div>
  );
}
