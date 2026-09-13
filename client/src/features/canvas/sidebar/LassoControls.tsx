// ── Free Select (Lasso) Tool Controls ────────────────────────────────────
import { useCanvasContext } from "../CanvasContext";
import styles from "./LassoControls.module.css";

export default function LassoControls() {
  const canvas = useCanvasContext();

  return (
    <div className={styles.panel}>

      {/* Antialiasing */}
      <label className={styles.clickableRow}>
        <input
          type="checkbox"
          className={styles.checkbox}
          checked={canvas.lassoAntialiasing}
          onChange={(e) => canvas.setLassoAntialiasing(e.target.checked)}
        />
        <span className={styles.label}>Antialiasing</span>
      </label>

      <div className={styles.divider} />

      {/* Feather edges */}
      <label className={styles.clickableRow}>
        <input
          type="checkbox"
          className={styles.checkbox}
          checked={canvas.lassoFeatherEdges}
          onChange={(e) => canvas.setLassoFeatherEdges(e.target.checked)}
        />
        <span className={styles.label}>Feather edges</span>
      </label>

      {/* Feather radius — only visible when feather is on */}
      {canvas.lassoFeatherEdges && (
        <div className={styles.row}>
          <span className={styles.subLabel}>
            Radius
          </span>
          <input
            type="range"
            min={0}
            max={100}
            step={0.5}
            value={canvas.lassoFeatherRadius}
            onChange={(e) => canvas.setLassoFeatherRadius(Number(e.target.value))}
            className={styles.slider}
            title={`Feather radius: ${canvas.lassoFeatherRadius.toFixed(1)} px`}
          />
          <input
            type="number"
            value={canvas.lassoFeatherRadius}
            onChange={(e) => canvas.setLassoFeatherRadius(Number(e.target.value))}
            onBlur={(e) =>
              canvas.setLassoFeatherRadius(
                Math.max(0, Math.min(100, Number(e.target.value))),
              )
            }
            className={styles.number}
          />
        </div>
      )}
    </div>
  );
}
