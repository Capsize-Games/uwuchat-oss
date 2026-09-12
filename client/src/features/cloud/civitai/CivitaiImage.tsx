import { useState, useEffect } from "react";
import { Image } from "lucide-react";
import styles from "./CivitaiImage.module.css";

interface CivitaiImageProps {
  url: string;
  alt: string;
  className?: string;
  style?: React.CSSProperties;
  width?: number;
  base64?: string;
}

/**
 * Renders a CivitAI image.
 *
 * - ``base64`` prop → data URI (from streaming events or server embeds).
 * - Spinner while waiting for ``base64`` to arrive.
 * - Fallback icon after a timeout when ``base64`` never materialises.
 */
export default function CivitaiImage({
  url: _url,
  alt: _alt,
  className,
  style,
  width: _desiredWidth,
  base64,
}: CivitaiImageProps) {
  const [failed, setFailed] = useState(false);

  /* ── Hide spinner after 15 s, show placeholder icon ── */
  const [timedOut, setTimedOut] = useState(false);
  useEffect(() => {
    if (base64) { setTimedOut(false); return; }
    const id = setTimeout(() => setTimedOut(true), 15_000);
    return () => clearTimeout(id);
  }, [base64]);

  if (base64 && !failed) {
    return (
      <img
        src={`data:image/jpeg;base64,${base64}`}
        alt=""
        className={className}
        style={style}
        loading="lazy"
        onError={() => setFailed(true)}
      />
    );
  }

  if (timedOut || failed) {
    return (
      <div
        className={`${styles.placeholder} ${className ?? ""}`}
        style={style}
      >
        <Image size={16} strokeWidth={2} className={styles.fallbackIcon} />
      </div>
    );
  }

  return (
    <div
      className={`${styles.placeholder} ${className ?? ""}`}
      style={style}
    >
      <div
        className={`spinner-border spinner-border-sm ${styles.spinner}`}
        role="status"
      >
        <span className="visually-hidden">Loading...</span>
      </div>
    </div>
  );
}
