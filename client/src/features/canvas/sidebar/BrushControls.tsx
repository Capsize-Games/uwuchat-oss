import { useRef } from "react";
import { useCanvasContext } from "../CanvasContext";
import styles from "./BrushControls.module.css";

export default function BrushControls() {
  const canvas = useCanvasContext();
  const colorInputRef = useRef<HTMLInputElement>(null);
  const brushActive = canvas.activeTool === "brush" || canvas.activeTool === "eraser";

  return (
    <div
      className={`d-flex align-items-center flex-shrink-0 border-b-subtle ${styles.root}`}
      // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
      style={{
        opacity: brushActive ? 1 : 0.35,
        pointerEvents: brushActive ? "auto" : "none",
      }}
    >
      <label title="Brush color" className="cursor-pointer flex-shrink-0 position-relative">
        <div
          className={styles.colorSwatch}
          // eslint-disable-next-line no-restricted-syntax -- canvas state-driven color/dimension
          style={{ background: canvas.brushColor }}
        />
        <input
          ref={colorInputRef}
          type="color"
          value={canvas.brushColor}
          onChange={(e) => canvas.setBrushColor(e.target.value)}
          className={styles.colorInputHidden}
          tabIndex={-1}
        />
      </label>

      <input
        type="range" min={1} max={200} step={1}
        value={canvas.brushSize}
        onChange={(e) => canvas.setBrushSize(Number(e.target.value))}
        className="flex-grow-1 min-w-0"
        title={`Brush size: ${canvas.brushSize}px`}
      />

      <input
        type="number"
        value={canvas.brushSize}
        onChange={(e) => canvas.setBrushSize(Number(e.target.value))}
        onBlur={(e) => canvas.setBrushSize(Math.max(1, Math.min(200, Number(e.target.value))))}
        className={styles.number}
      />
    </div>
  );
}
