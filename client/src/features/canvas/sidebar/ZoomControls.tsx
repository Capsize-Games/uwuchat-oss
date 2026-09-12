// ── Zoom Tool Controls ─────────────────────────────────────────────
import { useCanvasContext } from "../CanvasContext";
import styles from "./ZoomControls.module.css";

export default function ZoomControls() {
  const canvas = useCanvasContext();

  return (
    <div className={styles.panel}>
      {/* Direction — radio buttons */}
      <div className={styles.section}>
        <span className={styles.label}>Direction</span>

        <label className={styles.radioRow}>
          <input
            type="radio"
            name="zoomDirection"
            className={styles.radioInput}
            checked={canvas.zoomDirection === "in"}
            onChange={() => canvas.setZoomDirection("in")}
          />
          <span className={styles.radioLabel}>Zoom In</span>
        </label>

        <label className={styles.radioRow}>
          <input
            type="radio"
            name="zoomDirection"
            className={styles.radioInput}
            checked={canvas.zoomDirection === "out"}
            onChange={() => canvas.setZoomDirection("out")}
          />
          <span className={styles.radioLabel}>Zoom Out</span>
        </label>
      </div>
      <div className={styles.hint}>
        Click to zoom centered on pointer.{'\n'}
        Drag to marquee-zoom a region.
      </div>
    </div>
  );
}
