import styles from "./Toggle.module.css";

interface ToggleProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  ariaLabel: string;
  compact?: boolean;
}

export function Toggle({ checked, onChange, ariaLabel, compact }: ToggleProps) {
  const trackStyle = compact
    ? checked ? styles.trackOnCompact : styles.trackOffCompact
    : checked ? styles.trackOn : styles.trackOff;
  const knobStyle = compact
    ? checked ? styles.knobOnCompact : styles.knobOffCompact
    : checked ? styles.knobOn : styles.knobOff;

  return (
    <button type="button" role="switch" aria-checked={checked} aria-label={ariaLabel}
      onClick={() => onChange(!checked)}
      className={trackStyle}>
      <span className={knobStyle} />
    </button>
  );
}
