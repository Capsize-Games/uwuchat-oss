import { createPortal } from "react-dom";
import styles from "./GenTypePopup.module.css";
import shared from "./ArtShared.module.css";

interface GenTypePopupProps {
  anchor: { left: number; bottom: number } | null;
  generationType: "txt2img" | "img2img";
  onSelect: (v: "txt2img" | "img2img") => void;
}

export default function GenTypePopup({
  anchor,
  generationType,
  onSelect,
}: GenTypePopupProps) {
  if (!anchor) return null;

  return createPortal(
    <div
      id="art-gen-type-popup"
      className={`bg-theme-panel d-flex flex-column ${styles.popup}`}
      // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
      style={{
        left: anchor.left,
        bottom: anchor.bottom,
      }}
    >
      <div className={`${shared.sectionLabel} ${styles.headerRow}`}>
        Generation Type
      </div>

      <button
        type="button"
        onClick={() => onSelect("txt2img")}
        className={generationType === "txt2img" ? styles.genTypeBtnActive : styles.genTypeBtn}
      >
        <span>Text-to-image</span>
        <span className={styles.genTypeDesc}>
          Generate from a text description alone
        </span>
      </button>

      <button
        type="button"
        onClick={() => onSelect("img2img")}
        className={generationType === "img2img" ? styles.genTypeBtnActive : styles.genTypeBtn}
      >
        <span>Image-to-image</span>
        <span className={styles.genTypeDesc}>
          Transform an existing image with a text prompt
        </span>
      </button>
    </div>,
    document.body,
  );
}
