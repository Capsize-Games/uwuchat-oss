import { createPortal } from "react-dom";
import { saveToStorage } from "../art-model/ArtModelStorage";
import styles from "./SizePopup.module.css";
import shared from "./ArtShared.module.css";

interface SizePopupProps {
  anchor: { left: number; bottom: number } | null;
  portalId: string;
  genWidth: number;
  genHeight: number;
  onWidthChange: (v: number) => void;
  onHeightChange: (v: number) => void;
  persistGen: (updates: Record<string, unknown>) => void;
}

export default function SizePopup({
  anchor,
  portalId,
  genWidth,
  genHeight,
  onWidthChange,
  onHeightChange,
  persistGen,
}: SizePopupProps) {
  if (!anchor) return null;

  return createPortal(
    <div
      id={portalId}
      className={`d-flex flex-column bg-theme-panel ${styles.popup}`}
      // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
      style={{
        left: anchor.left,
        bottom: anchor.bottom,
      }}
    >
      <div className={shared.sectionLabel}>
        Image Size
      </div>
      <div className={`d-flex align-items-center ${styles.row}`}>
        <span className={styles.label}>W</span>
        <input
          type="number"
          className={`art-no-spin ${styles.input}`}
          value={genWidth}
          onChange={(e) => onWidthChange(Number(e.target.value))}
          onBlur={(e) => {
            const v = Math.max(
              64,
              Math.min(2048, Number(e.target.value)),
            );
            onWidthChange(v);
            saveToStorage("gen_width", v);
            persistGen({ width: v });
          }}
        />
      </div>
      <div className={`d-flex align-items-center ${styles.row}`}>
        <span className={styles.label}>H</span>
        <input
          type="number"
          className={`art-no-spin ${styles.input}`}
          value={genHeight}
          onChange={(e) => onHeightChange(Number(e.target.value))}
          onBlur={(e) => {
            const v = Math.max(
              64,
              Math.min(2048, Number(e.target.value)),
            );
            onHeightChange(v);
            saveToStorage("gen_height", v);
            persistGen({ height: v });
          }}
        />
      </div>
    </div>,
    document.body,
  );
}
