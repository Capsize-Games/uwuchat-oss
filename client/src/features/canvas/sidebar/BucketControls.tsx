// ── Bucket (Flood) Fill Tool Controls ──────────────────────────────────
import { useCanvasContext } from "../CanvasContext";
import styles from "./BucketControls.module.css";

export default function BucketControls() {
  const canvas = useCanvasContext();

  return (
    <div className={styles.panel}>
      {/* Color source */}
      <div className={styles.row}>
        <span className={styles.label}>Color source</span>
      </div>
      <div className={styles.radioGroup}>
        <label className={styles.radioRow}>
          <input
            type="radio"
            name="bucketColorSource"
            className={styles.radioCheckbox}
            checked={canvas.bucketColorSource === "foreground"}
            onChange={() =>
              canvas.setBucketColorSource("foreground")
            }
          />
          <span className={styles.radioLabel}>Foreground color</span>
        </label>
        <label className={styles.radioRow}>
          <input
            type="radio"
            name="bucketColorSource"
            className={styles.radioCheckbox}
            checked={canvas.bucketColorSource === "background"}
            onChange={() =>
              canvas.setBucketColorSource("background")
            }
          />
          <span className={styles.radioLabel}>Background color</span>
        </label>
      </div>

      <div className={styles.divider} />

      {/* Fill transparent areas */}
      <label className={styles.clickableRow}>
        <input
          type="checkbox"
          className={styles.checkbox}
          checked={canvas.bucketFillTransparentAreas}
          onChange={(e) =>
            canvas.setBucketFillTransparentAreas(e.target.checked)
          }
        />
        <span className={styles.label}>Fill transparent areas</span>
      </label>

      <div className={styles.divider} />

      {/* Antialiasing */}
      <label className={styles.clickableRow}>
        <input
          type="checkbox"
          className={styles.checkbox}
          checked={canvas.bucketAntialiasing}
          onChange={(e) =>
            canvas.setBucketAntialiasing(e.target.checked)
          }
        />
        <span className={styles.label}>Antialiasing</span>
      </label>

      <div className={styles.divider} />

      {/* Threshold */}
      <div className={styles.row}>
        <span className={styles.subLabel}>
          Threshold
        </span>
        <input
          type="range"
          min={0}
          max={100}
          step={0.5}
          value={canvas.bucketThreshold}
          onChange={(e) =>
            canvas.setBucketThreshold(Number(e.target.value))
          }
          className={styles.slider}
          title={`Threshold: ${canvas.bucketThreshold.toFixed(1)}`}
        />
        <input
          type="number"
          value={canvas.bucketThreshold}
          onChange={(e) => canvas.setBucketThreshold(Number(e.target.value))}
          onBlur={(e) =>
            canvas.setBucketThreshold(
              Math.max(0, Math.min(100, Number(e.target.value))),
            )
          }
          className={styles.number}
        />
      </div>
    </div>
  );
}
