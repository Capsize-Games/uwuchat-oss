import { useState, useRef, useEffect, useId } from "react";
import { createPortal } from "react-dom";
import LucideIcon from "../../shared/LucideIcon";
import styles from "./PromptToolbar.module.css";
import shared from "./ArtShared.module.css";

interface Props {
  genWidth: number;
  genHeight: number;
  onWidthChange: (v: number) => void;
  onHeightChange: (v: number) => void;
}

export function PromptToolbar({
  genWidth, genHeight,
  onWidthChange, onHeightChange,
}: Props) {
  const [showSize, setShowSize] = useState(false);
  const sizeContainerRef = useRef<HTMLDivElement>(null);
  const sizeBtnRef = useRef<HTMLButtonElement>(null);
  const [sizeAnchor, setSizeAnchor] = useState<{ left: number; bottom: number } | null>(null);
  const emittingRef = useRef(false);

  useEffect(() => {
    if (!showSize) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as Node;
      const portalEl = document.getElementById(portalId);
      if (portalEl?.contains(target)) return;
      if (sizeContainerRef.current && !sizeContainerRef.current.contains(target))
        setShowSize(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [showSize]);

  const portalId = useId();

  // Close when other overlays open
  useEffect(() => {
    const handler = () => {
      if (emittingRef.current) return;
      setShowSize(false);
    };
    window.addEventListener("art-overlay-opened", handler);
    window.addEventListener("chat-picker-opened", handler);
    return () => {
      window.removeEventListener("art-overlay-opened", handler);
      window.removeEventListener("chat-picker-opened", handler);
    };
  }, []);

  const handleSizeToggle = () => {
    const next = !showSize;
    setShowSize(next);
    if (next) {
      emittingRef.current = true;
      window.dispatchEvent(new Event("art-overlay-opened"));
      emittingRef.current = false;
      if (sizeBtnRef.current) {
        const r = sizeBtnRef.current.getBoundingClientRect();
        setSizeAnchor({ left: r.left, bottom: window.innerHeight - r.top + 4 });
      }
    }
  };

  return (
    <div className={styles.bar}>
      {/* Size picker */}
      <div ref={sizeContainerRef} className="position-relative">
        <button
          ref={sizeBtnRef}
          type="button"
          onClick={handleSizeToggle}
          className={showSize ? styles.sizeBtnActive : styles.sizeBtn}
        >
          {genWidth}×{genHeight}
        </button>
        {showSize && sizeAnchor && createPortal(
          <div id={portalId} className={`d-flex flex-column bg-theme-panel ${styles.sizePopup}`}
            // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
            style={{ left: sizeAnchor.left, bottom: sizeAnchor.bottom }}>
            <div className={shared.sectionLabel}>Image Size</div>
            <div className={`d-flex align-items-center ${styles.sizePopupRow}`}>
              <span className={styles.sizePopupLabel}>W</span>
              <input
                type="number" className={`art-no-spin ${styles.sizePopupInput}`}
                value={genWidth}
                onChange={(e) => onWidthChange(Number(e.target.value))}
                onBlur={(e) => onWidthChange(Math.max(64, Math.min(2048, Number(e.target.value))))}
              />
            </div>
            <div className={`d-flex align-items-center ${styles.sizePopupRow}`}>
              <span className={styles.sizePopupLabel}>H</span>
              <input
                type="number" className={`art-no-spin ${styles.sizePopupInput}`}
                value={genHeight}
                onChange={(e) => onHeightChange(Number(e.target.value))}
                onBlur={(e) => onHeightChange(Math.max(64, Math.min(2048, Number(e.target.value))))}
              />
            </div>
          </div>,
          document.body
        )}
      </div>
    </div>
  );
}
