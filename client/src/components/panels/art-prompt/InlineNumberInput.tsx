import styles from "./InlineNumberInput.module.css";

export default function InlineNumberInput({
  value,
  min,
  max,
  step,
  float,
  onChange,
  onClose,
}: {
  value: number;
  min: number;
  max: number;
  step?: number;
  float?: boolean;
  onChange: (v: number) => void;
  onClose: () => void;
}) {
  return (
    <div className={styles.wrap}>
      <input
        type="number"
        className={`art-no-spin ${styles.input}`}
        defaultValue={value}
        onBlur={(e) => {
          const v = float
            ? parseFloat(e.target.value)
            : parseInt(e.target.value, 10);
          if (!isNaN(v) && v >= min && v <= max) {
            onChange(v);
            onClose();
          }
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            const v = float
              ? parseFloat((e.target as HTMLInputElement).value)
              : parseInt((e.target as HTMLInputElement).value, 10);
            if (!isNaN(v) && v >= min && v <= max) {
              onChange(v);
              onClose();
            }
          }
        }}
        autoFocus
      />
      <span className={styles.hint}>
        (
        {float
          ? `${min.toFixed(1)}–${max.toFixed(1)}`
          : `${min}–${max}`}
        )
      </span>
    </div>
  );
}
