// ── Pipette (Color Picker) Tool Controls ──────────────────────────────
import { useCanvasContext } from "../CanvasContext";
import styles from "./PipetteControls.module.css";

export default function PipetteControls() {
  const canvas = useCanvasContext();

  return (
    <div className={styles.panel}>
      {/* Target routing — radio buttons */}
      <div className={styles.section}>
        <span className={styles.label}>Target</span>

        <label className={styles.radioRow}>
          <input
            type="radio"
            name="pipetteTarget"
            className={styles.radioInput}
            checked={canvas.pipetteTarget === "foreground"}
            onChange={() => canvas.setPipetteTarget("foreground")}
          />
          <span className={styles.radioLabel}>Set Foreground Color</span>
        </label>

        <label className={styles.radioRow}>
          <input
            type="radio"
            name="pipetteTarget"
            className={styles.radioInput}
            checked={canvas.pipetteTarget === "background"}
            onChange={() => canvas.setPipetteTarget("background")}
          />
          <span className={styles.radioLabel}>Set Background Color</span>
        </label>
      </div>

      {/* Current color swatches */}
      <div className={styles.section}>
        <span className={styles.label}>Current Colors</span>
        <div className={styles.swatchRow}>
          <div
            className={styles.swatch}
            // eslint-disable-next-line no-restricted-syntax -- canvas state-driven color/dimension
            style={{ background: canvas.brushColor }}
            title={canvas.brushColor}
          />
          <span className={styles.swatchLabel}>
            Foreground: <strong>{canvas.brushColor}</strong>
          </span>
        </div>
        <div className={styles.swatchRow}>
          <div
            className={styles.swatch}
            // eslint-disable-next-line no-restricted-syntax -- canvas state-driven color/dimension
            style={{ background: canvas.documentBgColor }}
            title={canvas.documentBgColor}
          />
          <span className={styles.swatchLabel}>
            Background: <strong>{canvas.documentBgColor}</strong>
          </span>
        </div>
      </div>

      <div className={styles.hint}>
        Click anywhere on the canvas to sample the exact pixel color
        under the cursor.
      </div>
    </div>
  );
}
