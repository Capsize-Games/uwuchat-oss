// ── Crop Tool Controls ──────────────────────────────────────────────────
// Two-way bound sliders for crop position (X/Y) and size (Width/Height).
// Changes here update the Konva crop rect in real time;
// Konva Transformer changes update these sliders in real time.

import { useCanvasContext } from "../CanvasContext";
import styles from "./CropControls.module.css";

export default function CropControls() {
  const canvas = useCanvasContext();

  return (
    <div className={styles.panel}>
      {/* Position */}
      <div className={styles.sectionLabel}>Position</div>

      <div className={styles.row}>
        <span className={styles.label}>X</span>
        <input
          type="range"
          min={0}
          max={canvas.documentWidth}
          step={1}
          value={canvas.cropX}
          onChange={(e) => canvas.setCropX(Number(e.target.value))}
          className={styles.slider}
          title={`Crop X: ${canvas.cropX} px`}
        />
        <input
          type="number"
          value={canvas.cropX}
          onChange={(e) => canvas.setCropX(Number(e.target.value))}
          onBlur={(e) =>
            canvas.setCropX(
              Math.max(0, Math.min(canvas.documentWidth, Number(e.target.value))),
            )
          }
          className={styles.number}
        />
      </div>

      <div className={styles.row}>
        <span className={styles.label}>Y</span>
        <input
          type="range"
          min={0}
          max={canvas.documentHeight}
          step={1}
          value={canvas.cropY}
          onChange={(e) => canvas.setCropY(Number(e.target.value))}
          className={styles.slider}
          title={`Crop Y: ${canvas.cropY} px`}
        />
        <input
          type="number"
          value={canvas.cropY}
          onChange={(e) => canvas.setCropY(Number(e.target.value))}
          onBlur={(e) =>
            canvas.setCropY(
              Math.max(0, Math.min(canvas.documentHeight, Number(e.target.value))),
            )
          }
          className={styles.number}
        />
      </div>

      <div className={styles.divider} />

      {/* Size */}
      <div className={styles.sectionLabel}>Size</div>

      <div className={styles.row}>
        <span className={styles.label}>W</span>
        <input
          type="range"
          min={1}
          max={canvas.documentWidth}
          step={1}
          value={canvas.cropWidth}
          onChange={(e) => canvas.setCropWidth(Number(e.target.value))}
          className={styles.slider}
          title={`Crop width: ${canvas.cropWidth} px`}
        />
        <input
          type="number"
          value={canvas.cropWidth}
          onChange={(e) => canvas.setCropWidth(Number(e.target.value))}
          onBlur={(e) =>
            canvas.setCropWidth(
              Math.max(1, Math.min(canvas.documentWidth, Number(e.target.value))),
            )
          }
          className={styles.number}
        />
      </div>

      <div className={styles.row}>
        <span className={styles.label}>H</span>
        <input
          type="range"
          min={1}
          max={canvas.documentHeight}
          step={1}
          value={canvas.cropHeight}
          onChange={(e) => canvas.setCropHeight(Number(e.target.value))}
          className={styles.slider}
          title={`Crop height: ${canvas.cropHeight} px`}
        />
        <input
          type="number"
          value={canvas.cropHeight}
          onChange={(e) => canvas.setCropHeight(Number(e.target.value))}
          onBlur={(e) =>
            canvas.setCropHeight(
              Math.max(1, Math.min(canvas.documentHeight, Number(e.target.value))),
            )
          }
          className={styles.number}
        />
      </div>

      <div className={styles.divider} />

      <div className={styles.hint}>
        Draw a rectangle on the canvas, then drag handles to adjust.
        Press <b>Enter</b> to commit or <b>Esc</b> to cancel.
      </div>
    </div>
  );
}
