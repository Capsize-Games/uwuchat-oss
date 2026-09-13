import { useState, useRef, useEffect } from "react";
import { createPortal } from "react-dom";
import Form from "react-bootstrap/Form";
import LucideIcon from "../shared/LucideIcon";
import styles from "./ProviderPicker.module.css";

const PROVIDERS = [
  { value: "local", label: "Local" },
  { value: "openrouter", label: "OpenRouter" },
  { value: "ollama", label: "Ollama" },
  { value: "openai", label: "OpenAI" },
];

interface Props {
  value: string;
  apiKey: string;
  apiBaseUrl: string;
  statusDotColor: string;
  statusDotTitle: string;
  onChangeProvider: (v: string) => void;
  onChangeApiKey: (v: string) => void;
  onChangeApiBaseUrl: (v: string) => void;
}

export function ProviderPicker({
  value,
  apiKey,
  apiBaseUrl,
  statusDotColor,
  statusDotTitle,
  onChangeProvider,
  onChangeApiKey,
  onChangeApiBaseUrl,
}: Props) {
  const [open, setOpen] = useState(false);
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
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  useEffect(() => {
    const handler = () => setOpen(false);
    window.addEventListener("art-overlay-opened", handler);
    return () => window.removeEventListener("art-overlay-opened", handler);
  }, []);

  const label = PROVIDERS.find((p) => p.value === value)?.label ?? value;
  const isOllama = value === "ollama";
  const needsApiKey = value === "openrouter" || value === "openai";

  return (
    <div ref={containerRef} className={styles.container}>
      <button
        ref={btnRef}
        type="button"
        onClick={openPicker}
        title={statusDotTitle}
        className={styles.triggerBtn}
      >
        <span
          className={styles.statusDot}
          // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
          style={{ backgroundColor: statusDotColor }}
        />
        {label}
        <LucideIcon name="chevrons-up-down" size={11} />
      </button>

      {open && anchor && createPortal(
        <div
          ref={popupRef}
          className={`bg-theme-panel ${styles.popup}`}
          // eslint-disable-next-line no-restricted-syntax -- portal position from measured DOM rect
          style={{ left: anchor.left, bottom: anchor.bottom }}
        >
          {PROVIDERS.map((p) => {
            const isActive = p.value === value;
            return (
              <button
                key={p.value}
                type="button"
                onClick={() => {
                  onChangeProvider(p.value);
                  const stillNeedsInput =
                    p.value === "ollama" ||
                    p.value === "openrouter" ||
                    p.value === "openai";
                  if (!stillNeedsInput) setOpen(false);
                }}
                className={`${styles.listItem} ${isActive ? styles.listItemActive : styles.listItemInactive}`}
              >
                {p.label}
              </button>
            );
          })}

          {(isOllama || needsApiKey) && (
            <div className={`d-flex flex-column border-t-subtle ${styles.configSection}`}>
              {isOllama && (
                <Form.Control
                  size="sm"
                  value={apiBaseUrl}
                  onChange={(e) => onChangeApiBaseUrl(e.target.value)}
                  placeholder="Ollama URL (default: http://localhost:11434)"
                  className={styles.configInput}
                  autoFocus
                />
              )}
              {needsApiKey && (
                <Form.Control
                  size="sm"
                  type="password"
                  value={apiKey}
                  onChange={(e) => onChangeApiKey(e.target.value)}
                  placeholder={`${label} API key`}
                  className={styles.configInput}
                  autoFocus
                />
              )}
            </div>
          )}
        </div>,
        document.body
      )}
    </div>
  );
}
