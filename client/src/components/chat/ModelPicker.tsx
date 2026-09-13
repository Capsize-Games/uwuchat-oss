import { useState, useRef, useEffect } from "react";
import { createPortal } from "react-dom";
import Form from "react-bootstrap/Form";
import LucideIcon from "../shared/LucideIcon";
import styles from "./ModelPicker.module.css";

interface Props {
  value: string;
  provider: string;
  localModels: { label: string; value: string }[];
  onChangeModel: (v: string) => void;
}

export function ModelPicker({
  value,
  provider,
  localModels,
  onChangeModel,
}: Props) {
  const isLocal = provider === "local";
  const isOllama = provider === "ollama";
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);
  const popupRef = useRef<HTMLDivElement>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const [anchor, setAnchor] = useState<{ left: number; bottom: number } | null>(null);

  const openPicker = () => {
    setOpen((v) => {
      const next = !v;
      if (next) {
        window.dispatchEvent(new Event("chat-picker-opened"));
        if (btnRef.current) {
          const r = btnRef.current.getBoundingClientRect();
          setAnchor({ left: r.left, bottom: window.innerHeight - r.top + 4 });
        }
      }
      return next;
    });
  };

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as Node;
      if (containerRef.current?.contains(target)) return;
      if (popupRef.current?.contains(target)) return;
      setOpen(false);
      setQuery("");
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  useEffect(() => {
    const handler = () => setOpen(false);
    window.addEventListener("art-overlay-opened", handler);
    return () => window.removeEventListener("art-overlay-opened", handler);
  }, []);

  const stripPathAndExt = (s: string) =>
    (s.split("/").pop() ?? s).replace(/\.(gguf|bin|safetensors|pt|pth|ckpt|pkl|model)$/i, "");

  const displayLabel = isLocal
    ? stripPathAndExt(
        localModels.find((m) => m.value === value)?.label ??
        (value || "Select model…")
      )
    : value || (isOllama ? "Model name…" : "Model ID…");

  const filtered = localModels.filter(
    (m) => !query || m.label.toLowerCase().includes(query.toLowerCase()),
  );

  return (
    <div ref={containerRef} className={styles.container}>
      <button
        ref={btnRef}
        type="button"
        onClick={openPicker}
        title={value || "Select model"}
        className={styles.triggerBtn}
        // eslint-disable-next-line no-restricted-syntax -- canvas state-driven color/dimension
        style={{ color: value ? "var(--theme-text)" : "rgba(255,255,255,0.35)" }}
      >
        <span className={styles.triggerLabel}>
          {displayLabel}
        </span>
        <LucideIcon name="chevrons-up-down" size={11} />
      </button>

      {open && anchor && createPortal(
        <div
          ref={popupRef}
          className={`d-flex flex-column bg-theme-panel ${styles.popup}`}
          // eslint-disable-next-line no-restricted-syntax -- portal position from measured DOM rect
          style={{ left: anchor.left, bottom: anchor.bottom }}
        >
          {isLocal ? (
            <>
              <div className={styles.searchInput}>
                <Form.Control
                  size="sm"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search models…"
                  className={styles.searchFormControl}
                  autoFocus
                />
              </div>
              <div className="overflow-y-auto flex-grow-1">
                {filtered.length === 0 && (
                  <div className={styles.emptyText}>
                    No models found
                  </div>
                )}
                {filtered.map((m) => {
                  const isActive = m.value === value;
                  return (
                    <button
                      key={m.value}
                      type="button"
                      onClick={() => {
                        onChangeModel(m.value);
                        setOpen(false);
                        setQuery("");
                      }}
                      className={`${styles.listItem} ${isActive ? styles.listItemActive : styles.listItemInactive}`}
                    >
                      {m.label}
                    </button>
                  );
                })}
              </div>
            </>
          ) : (
            <div className={styles.inputWrapper}>
              <Form.Control
                size="sm"
                value={value}
                onChange={(e) => onChangeModel(e.target.value)}
                placeholder={isOllama ? "Model name (e.g. llama3)" : "Model ID"}
                className={styles.formInput}
                autoFocus
              />
            </div>
          )}
        </div>,
        document.body,
      )}
    </div>
  );
}
