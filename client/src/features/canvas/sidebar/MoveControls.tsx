// ── Move Tool Controls ──────────────────────────────────────────────
import { useCanvasContext } from "../CanvasContext";
import type { MoveMode } from "../canvasTypes";
import styles from "./MoveControls.module.css";

const OPTIONS: { value: MoveMode; label: string }[] = [
  { value: "pick",          label: "Pick a layer or guide" },
  { value: "move-selected", label: "Move the selected layers" },
];

export default function MoveControls() {
  const canvas = useCanvasContext();

  return (
    <div className={styles.root}>
      {OPTIONS.map((opt) => {
        const isActive = canvas.moveMode === opt.value;
        return (
          <button
            key={opt.value}
            type="button"
            onClick={() => canvas.setMoveMode(opt.value)}
            className={`${styles.optionBtn} ${isActive ? styles.optionBtnActive : ""}`}
          >
            <div
              className={`${styles.radioDot} ${isActive ? styles.radioDotActive : styles.radioDotInactive}`}
            />
            {opt.label}
          </button>
        );
      })}

      {/* ── Snap to grid ─────────────────────────────────────────────── */}
      <div className={styles.snapSection}>
        <label className={styles.snapLabel}>
          <input
            type="checkbox"
            checked={canvas.snapToGrid}
            onChange={(e) => canvas.setSnapToGrid(e.target.checked)}
            className={styles.snapCheckbox}
          />
          <span className={styles.snapText}>
            Snap to Grid
          </span>
        </label>
      </div>
    </div>
  );
}
