// ── Text Tool Controls ─────────────────────────────────────────────────
// Font family dropdown, font size input, and color picker for the text
// tool.  Changes update global text settings and, if a text node is
// actively being edited, apply immediately to the active node.

import { useCanvasContext } from "../CanvasContext";
import styles from "./TextControls.module.css";

// ── Web-safe font stack ──────────────────────────────────────────────────

const FONTS = [
  "Arial",
  "Verdana",
  "Helvetica",
  "Tahoma",
  "Trebuchet MS",
  "Times New Roman",
  "Georgia",
  "Garamond",
  "Courier New",
  "Brush Script MT",
  "Impact",
  "Comic Sans MS",
];

// ── Component ────────────────────────────────────────────────────────────

export default function TextControls() {
  const canvas = useCanvasContext();

  return (
    <div className={styles.panel}>
      {/* Font family */}
      <div className={styles.section}>
        <span className={styles.label}>Font</span>
        <select
          className={styles.select}
          value={canvas.textFont}
          onChange={(e) => canvas.setTextFont(e.target.value)}
        >
          {FONTS.map((f) => (
            <option key={f} value={f}>
              {f}
            </option>
          ))}
        </select>
      </div>

      {/* Font size */}
      <div className={styles.section}>
        <span className={styles.label}>Size</span>
        <div className={styles.inputRow}>
          <input
            type="number"
            className={styles.numberInput}
            value={canvas.textSize}
            onChange={(e) => {
              const v = parseInt(e.target.value, 10);
              if (!isNaN(v)) canvas.setTextSize(v);
            }}
            onBlur={(e) => {
              const v = parseInt(e.target.value, 10);
              if (!isNaN(v)) canvas.setTextSize(Math.max(1, v));
            }}
          />
          <span className={styles.unit}>
            px
          </span>
        </div>
      </div>

      {/* Color */}
      <div className={styles.section}>
        <span className={styles.label}>Color</span>
        <div className={styles.inputRow}>
          <input
            type="color"
            className={styles.colorInput}
            value={canvas.textColor}
            onChange={(e) => canvas.setTextColor(e.target.value)}
          />
          <span className={styles.colorValue}>
            {canvas.textColor}
          </span>
        </div>
      </div>

      <div className={styles.hint}>
        Click anywhere on the canvas to place text. Type to edit,
        then click elsewhere to finish.
      </div>
    </div>
  );
}
