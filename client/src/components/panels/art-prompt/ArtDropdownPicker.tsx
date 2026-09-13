 import { useState, useRef, useEffect, useId } from "react";
import { createPortal } from "react-dom";
import LucideIcon from "../../shared/LucideIcon";
import styles from "./ArtDropdownPicker.module.css";

interface Props {
  value: string;
  placeholder: string;
  options: { label: string; value: string }[];
  onChange: (v: string) => void;
  disabled?: boolean;
}

export function ArtDropdownPicker({
  value,
  placeholder,
  options,
  onChange,
  disabled,
}: Props) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const [anchor, setAnchor] = useState<{ left: number; bottom: number; width: number } | null>(null);
  const emittingRef = useRef(false);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as Node;
      const portalEl = document.getElementById(portalId);
      if (portalEl?.contains(target)) return;
      if (containerRef.current && !containerRef.current.contains(target)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const portalId = useId();

  // Close when other overlays open
  useEffect(() => {
    const handler = () => {
      if (emittingRef.current) return;
      setOpen(false);
    };
    window.addEventListener("art-overlay-opened", handler);
    window.addEventListener("chat-picker-opened", handler);
    return () => {
      window.removeEventListener("art-overlay-opened", handler);
      window.removeEventListener("chat-picker-opened", handler);
    };
  }, []);

  const rawLabel = options.find((o) => o.value === value)?.label ?? (value || placeholder);
  const label = rawLabel === placeholder
    ? rawLabel
    : (rawLabel.split("/").pop() ?? rawLabel).replace(/\.(gguf|bin|safetensors|pt|pth|ckpt|pkl|model|safetensor)$/i, "");

  const handleToggle = () => {
    if (disabled) return;
    const next = !open;
    setOpen(next);
    if (next) {
      emittingRef.current = true;
      window.dispatchEvent(new Event("art-overlay-opened"));
      emittingRef.current = false;
      if (btnRef.current) {
        const r = btnRef.current.getBoundingClientRect();
        setAnchor({ left: r.left, bottom: window.innerHeight - r.top + 4, width: r.width });
      }
    }
  };

  const triggerBtnCls = disabled
    ? styles.triggerBtnDisabled
    : styles.triggerBtnEnabled;
  const labelCls = value
    ? styles.triggerLabelValue
    : styles.triggerLabelPlaceholder;

  return (
    <div ref={containerRef} className={`min-w-0 ${styles.trigger}`}>
      <button
        ref={btnRef}
        type="button"
        disabled={disabled}
        onClick={handleToggle}
        title={label}
        className={triggerBtnCls}
      >
        <span className={`${styles.triggerLabel} ${labelCls}`}>
          {label}
        </span>
        <LucideIcon name="chevrons-up-down" size={11} />
      </button>

      {open && !disabled && anchor && createPortal(
        <div
          id={portalId}
          className={`bg-theme-panel overflow-y-auto ${styles.dropdown}`}
          data-dropdown-portal=""
          // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
          style={{
            left: anchor.left,
            bottom: anchor.bottom,
            minWidth: Math.max(anchor.width, 160),
            maxWidth: 280,
          }}
        >
          {options.length === 0 ? (
            <div className={styles.noOptions}>No options</div>
          ) : (
            options.map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => {
                  onChange(opt.value);
                  setOpen(false);
                }}
                className={opt.value === value ? styles.optActive : styles.opt}
              >
                {opt.label}
              </button>
            ))
          )}
        </div>,
        document.body
      )}
    </div>
  );
}
