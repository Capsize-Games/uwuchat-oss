// ── Image Context Menu ──────────────────────────────────────────────────
// Right-click context menu for image rows in the image browser.
// Accepts an array of action items; each can trigger a callback.

// Also exports helpers so consumers (ServerImageRow / LocalImageRow) can
// wire up the "export" action inline without duplicating save logic.
// ──────────────────────────────────────────────────────────────────────────
import { useEffect, useRef } from "react";
import { getRequestHeaders } from "virtual:extensions";
import { BASE_URL } from "../../../types/api";
import LucideIcon from "../../shared/LucideIcon";
import styles from "./ImageContextMenu.module.css";

export interface ContextMenuAction {
  label: string;
  icon: string;
  onClick: () => void;
  /** Render with destructive (red) styling. */
  danger?: boolean;
}

interface Props {
  x: number;
  y: number;
  actions: (ContextMenuAction | "divider")[];
  onClose: () => void;
}

export default function ImageContextMenu({
  x,
  y,
  actions,
  onClose,
}: Props) {
  const menuRef = useRef<HTMLDivElement>(null);

  // Dismiss on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (
        menuRef.current &&
        !menuRef.current.contains(e.target as Node)
      ) {
        onClose();
      }
    };
    const timer = setTimeout(() => {
      window.addEventListener("mousedown", handler);
    }, 0);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("mousedown", handler);
    };
  }, [onClose]);

  // Dismiss on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  const adjustedY = Math.min(
    y,
    window.innerHeight - actions.length * 32 - 20,
  );
  const adjustedX = Math.min(x, window.innerWidth - 190);

  return (
    <div
      ref={menuRef}
      className={styles.menu}
      // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
      style={{ left: adjustedX, top: adjustedY }}
    >
      {actions.map((entry, i) => {
        if (entry === "divider") {
          return <div key={`div-${i}`} className={styles.divider} />;
        }

        return (
          <button
            key={`action-${i}`}
            type="button"
            className={entry.danger ? styles.itemDanger : styles.item}
            onClick={() => {
              entry.onClick();
              onClose();
            }}
          >
            <LucideIcon name={entry.icon} size={13} />
            <span>{entry.label}</span>
          </button>
        );
      })}
    </div>
  );
}

// ── Export helpers (reused by ServerImageRow / LocalImageRow) ───────────

/**
 * Fetch a server-side image through the same auth layer used by
 * `useAuthenticatedBlobUrl` but as a one-shot Promise.
 */
export async function fetchImageBlob(
  apiPath: string,
): Promise<Blob> {
  const headers = getRequestHeaders();
  const url = `${BASE_URL}${apiPath}`;
  const res = await fetch(url, { headers });
  if (!res.ok) throw new Error(`Fetch failed: ${res.status}`);
  return res.blob();
}

/** Convert a `data:` URL to a Blob. */
export function dataUrlToBlob(dataUrl: string): Blob {
  const [header, b64] = dataUrl.split(",");
  const mime =
    header.match(/:(.*?);/)?.[1] ?? "image/png";
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return new Blob([bytes], { type: mime });
}

/**
 * Present the platform save dialog (showSaveFilePicker when available)
 * or trigger an immediate download as fallback.
 */
export async function saveBlobToDisk(
  blob: Blob,
  fileName: string,
): Promise<void> {
  if ("showSaveFilePicker" in window) {
    try {
      const handle = await (
        window as Window & typeof globalThis
      ).showSaveFilePicker({
        suggestedName: fileName,
        types: [
          {
            description: "PNG Image",
            accept: { "image/png": [".png"] },
          },
        ],
      });
      const writable = await handle.createWritable();
      await writable.write(blob);
      await writable.close();
      return;
    } catch (err: unknown) {
      if (
        err instanceof DOMException &&
        err.name === "AbortError"
      ) {
        return;
      }
    }
  }

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
