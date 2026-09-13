// ── Grid Tool Controls ─────────────────────────────────────────────
import { useRef } from "react";
import { useCanvasContext } from "../CanvasContext";
import styles from "./GridControls.module.css";

export default function GridControls() {
  const canvas = useCanvasContext();
  const colorInputRef = useRef<HTMLInputElement>(null);

  return (
    <div className={styles.panel}>
      {/* Show grid checkbox */}
      <div className={styles.row}>
        <label className={styles.checkboxLabel}>
          <input
            type="checkbox"
            checked={canvas.gridShowGrid}
            onChange={(e) => canvas.setGridShowGrid(e.target.checked)}
            className={styles.checkbox}
          />
          <span className={styles.checkboxText}>
            Show Grid
          </span>
        </label>
      </div>

      {/* Grid size slider + spinbox */}
      <div className={styles.row}>
        <span className={styles.label}>Size</span>
        <input
          type="range"
          min={8}
          max={512}
          step={8}
          value={canvas.gridSize}
          onChange={(e) => canvas.setGridSize(Number(e.target.value))}
          className={styles.slider}
          title={`Grid size: ${canvas.gridSize}px`}
        />
        <input
          type="number"
          value={canvas.gridSize}
          onChange={(e) => canvas.setGridSize(Number(e.target.value))}
          onBlur={(e) =>
            canvas.setGridSize(
              Math.max(8, Math.min(512, Number(e.target.value))),
            )
          }
          className={styles.number}
        />
      </div>

      {/* Grid color selector */}
      <div className={styles.row}>
        <span className={styles.label}>Color</span>
        <label title="Grid color" className="cursor-pointer position-relative">
          <div
            className={styles.colorSwatch}
            // eslint-disable-next-line no-restricted-syntax -- canvas state-driven color/dimension
            style={{ background: canvas.gridColor }}
          />
          <input
            ref={colorInputRef}
            type="color"
            value={canvas.gridColor}
            onChange={(e) => canvas.setGridColor(e.target.value)}
            className={styles.colorInputHidden}
            tabIndex={-1}
          />
        </label>
      </div>
    </div>
  );
}
