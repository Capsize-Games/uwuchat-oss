// ── Fuzzy Select (Magic Wand) Tool Controls ──────────────────────────────
import { useCanvasContext } from "../CanvasContext";
import styles from "./WandControls.module.css";

export default function WandControls() {
  const canvas = useCanvasContext();

  return (
    <div className={styles.panel}>

      {/* Antialiasing */}
      <label className={styles.clickableRow}>
        <input
          type="checkbox"
          className={styles.checkbox}
          checked={canvas.wandAntialiasing}
          onChange={(e) => canvas.setWandAntialiasing(e.target.checked)}
        />
        <span className={styles.label}>Antialiasing</span>
      </label>

      <div className={styles.divider} />

      {/* Feather edges */}
      <label className={styles.clickableRow}>
        <input
          type="checkbox"
          className={styles.checkbox}
          checked={canvas.wandFeatherEdges}
          onChange={(e) => canvas.setWandFeatherEdges(e.target.checked)}
        />
        <span className={styles.label}>Feather edges</span>
      </label>

      {/* Feather radius — only visible when feather is on */}
      {canvas.wandFeatherEdges && (
        <div className={styles.row}>
          <span className={styles.subLabel}>
            Radius
          </span>
          <input
            type="range"
            min={0}
            max={100}
            step={0.5}
            value={canvas.wandFeatherRadius}
            onChange={(e) => canvas.setWandFeatherRadius(Number(e.target.value))}
            className={styles.slider}
            title={`Feather radius: ${canvas.wandFeatherRadius.toFixed(1)} px`}
          />
          <input
            type="number"
            value={canvas.wandFeatherRadius}
            onChange={(e) => canvas.setWandFeatherRadius(Number(e.target.value))}
            onBlur={(e) =>
              canvas.setWandFeatherRadius(
                Math.max(0, Math.min(100, Number(e.target.value))),
              )
            }
            className={styles.number}
          />
        </div>
      )}

      <div className={styles.divider} />

      {/* Select transparent areas */}
      <label className={styles.clickableRow}>
        <input
          type="checkbox"
          className={styles.checkbox}
          checked={canvas.wandSelectTransparentAreas}
          onChange={(e) => canvas.setWandSelectTransparentAreas(e.target.checked)}
        />
        <span className={styles.label}>Select transparent areas</span>
      </label>

      <div className={styles.divider} />

      {/* Sample merged */}
      <label className={styles.clickableRow}>
        <input
          type="checkbox"
          className={styles.checkbox}
          checked={canvas.wandSampleMerged}
          onChange={(e) => canvas.setWandSampleMerged(e.target.checked)}
        />
        <span className={styles.label}>Sample merged</span>
      </label>

      <div className={styles.divider} />

      {/* Diagonal neighbors */}
      <label className={styles.clickableRow}>
        <input
          type="checkbox"
          className={styles.checkbox}
          checked={canvas.wandDiagonalNeighbors}
          onChange={(e) => canvas.setWandDiagonalNeighbors(e.target.checked)}
        />
        <span className={styles.label}>Diagonal neighbors</span>
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
          value={canvas.wandThreshold}
          onChange={(e) => canvas.setWandThreshold(Number(e.target.value))}
          className={styles.slider}
          title={`Threshold: ${canvas.wandThreshold.toFixed(1)}`}
        />
        <input
          type="number"
          value={canvas.wandThreshold}
          onChange={(e) => canvas.setWandThreshold(Number(e.target.value))}
          onBlur={(e) =>
            canvas.setWandThreshold(
              Math.max(0, Math.min(100, Number(e.target.value))),
            )
          }
          className={styles.number}
        />
      </div>

    </div>
  );
}
