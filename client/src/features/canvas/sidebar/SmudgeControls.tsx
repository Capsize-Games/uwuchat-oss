// ── Smudge Tool Controls ────────────────────────────────────────────────
import { useCanvasContext } from "../CanvasContext";
import styles from "./SmudgeControls.module.css";

export default function SmudgeControls() {
  const canvas = useCanvasContext();

  return (
    <div className={styles.panel}>
      {/* Brush size */}
      <div className={styles.row}>
        <span className={styles.subLabel}>
          Size
        </span>
        <input
          type="range"
          min={0}
          max={100}
          step={0.5}
          value={canvas.smudgeSize}
          onChange={(e) =>
            canvas.setSmudgeSize(Number(e.target.value))
          }
          className={styles.slider}
          title={`Smudge size: ${canvas.smudgeSize.toFixed(1)}`}
        />
        <input
          type="number"
          value={canvas.smudgeSize}
          onChange={(e) => canvas.setSmudgeSize(Number(e.target.value))}
          onBlur={(e) =>
            canvas.setSmudgeSize(
              Math.max(0, Math.min(100, Number(e.target.value))),
            )
          }
          className={styles.number}
        />
      </div>

      <div className={styles.hint}>
        Click and drag over an image to smear pixels along
        your stroke path.
      </div>
    </div>
  );
}
