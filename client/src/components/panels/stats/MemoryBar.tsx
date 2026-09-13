import styles from "./MemoryBar.module.css";

interface Props {
  label: string;
  usedGb: number;
  totalGb: number;
  highColor: string;
  lowColor: string;
}

export default function MemoryBar({ label, usedGb, totalGb, highColor, lowColor }: Props) {
  const pct = totalGb > 0 ? (usedGb / totalGb) * 100 : 0;
  return (
    <div className="mb-2">
      <small className="text-muted">{label}</small>
      <div className={styles.outer}>
        <div
          className={styles.fill}
          // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
          style={{
            width: `${Math.min(pct, 100)}%`,
            backgroundColor: pct > 90 ? highColor : lowColor,
          }}
        />
      </div>
      <small className="text-muted">
        {usedGb.toFixed(1)} / {totalGb.toFixed(1)} GB
      </small>
    </div>
  );
}
