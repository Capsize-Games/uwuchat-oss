// ── Ruler Tool Controls ───────────────────────────────────────────
import { useCanvasContext } from "../CanvasContext";
import styles from "./RulerControls.module.css";

export default function RulerControls() {
  const canvas = useCanvasContext();

  return (
    <div className={styles.panel}>
      <div className={styles.row}>
        <label className={styles.checkboxLabel}>
          <input
            type="checkbox"
            checked={canvas.rulerShowRuler}
            onChange={(e) => canvas.setRulerShowRuler(e.target.checked)}
            className={styles.checkbox}
          />
          <span className={styles.checkboxText}>
            Show Ruler
          </span>
        </label>
      </div>
    </div>
  );
}
