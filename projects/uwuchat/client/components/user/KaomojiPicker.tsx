import React, { useState, useRef, useEffect } from "react";
import { KAOMOJI_CATEGORIES } from "../../data/kaomoji";
import styles from "./KaomojiPicker.module.css";

const PANEL_W = 240;

interface KaomojiPickerProps {
  value: string;
  isOwnProfile: boolean;
  onSave: (kaomoji: string) => void;
}

export default function KaomojiPicker({
  value,
  isOwnProfile,
  onSave,
}: KaomojiPickerProps) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number }>({ top: 0, left: 0 });
  const [tab, setTab] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  const handleOpen = () => {
    if (!isOwnProfile) return;
    const rect = buttonRef.current?.getBoundingClientRect();
    if (!rect) return;
    const left = Math.max(8, Math.min(rect.left, window.innerWidth - PANEL_W - 12));
    setPos({ top: rect.bottom + 6, left });
    setOpen(true);
  };

  const handleSelect = (k: string) => {
    onSave(k);
    setOpen(false);
  };

  if (!value && !isOwnProfile) return null;

  const btnClass = isOwnProfile
    ? styles.triggerBtnClickable
    : styles.triggerBtnDisabled;

  return (
    <div ref={containerRef} className={styles.container}>
      <button
        ref={buttonRef}
        onClick={handleOpen}
        disabled={!isOwnProfile}
        className={btnClass}
      >
        {value || "+ kaomoji"}
      </button>

      {open && (
        <div
          className={styles.panel}
          // eslint-disable-next-line no-restricted-syntax -- portal position from measured DOM rect
          style={{ top: pos.top, left: pos.left }}
        >
          <div className={styles.catRow}>
            <select
              value={tab}
              onChange={(e) => setTab(Number(e.target.value))}
              className={styles.catSelect}
            >
              {KAOMOJI_CATEGORIES.map((cat, i) => (
                <option key={cat.label} value={i}>
                  {cat.label}
                </option>
              ))}
            </select>
          </div>

          <div className={styles.faceList}>
            {KAOMOJI_CATEGORIES[tab].faces.map((k) => (
              <button
                key={k}
                onClick={() => handleSelect(k)}
                className={
                  value === k ? styles.faceBtnSelected : styles.faceBtn
                }
              >
                {k}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
