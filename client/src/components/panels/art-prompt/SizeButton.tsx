import type { RefObject } from "react";
import LucideIcon from "../../shared/LucideIcon";
import SizePopup from "./SizePopup";
import styles from "./SizeButton.module.css";

interface SizeButtonProps {
  sizeBtnRef: RefObject<HTMLDivElement | null>;
  showSize: boolean;
  toggleSize: () => void;
  sizeAnchor: { left: number; bottom: number } | null;
  sizePortalId: string;
  genWidth: number;
  genHeight: number;
  onWidthChange: (v: number) => void;
  onHeightChange: (v: number) => void;
  persistGen: (updates: Record<string, unknown>) => void;
}

export default function SizeButton({
  sizeBtnRef,
  showSize,
  toggleSize,
  sizeAnchor,
  sizePortalId,
  genWidth,
  genHeight,
  onWidthChange,
  onHeightChange,
  persistGen,
}: SizeButtonProps) {
  return (
    <>
      <div ref={sizeBtnRef}>
        <button
          type="button"
          title="Image size"
          onClick={toggleSize}
          className={showSize ? styles.btnActive : styles.btn}
        >
          <LucideIcon name="ruler-dimension-line" size={13} />
        </button>
      </div>
      <SizePopup
        anchor={showSize ? sizeAnchor : null}
        portalId={sizePortalId}
        genWidth={genWidth}
        genHeight={genHeight}
        onWidthChange={onWidthChange}
        onHeightChange={onHeightChange}
        persistGen={persistGen}
      />
    </>
  );
}
