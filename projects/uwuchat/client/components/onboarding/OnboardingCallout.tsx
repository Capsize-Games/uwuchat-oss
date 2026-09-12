import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import Button from "react-bootstrap/Button";
import { useTranslation } from "react-i18next";
import { useIsMobile } from "../../hooks/useIsMobile";
import styles from "./OnboardingCallout.module.css";

interface Position { top: number; left: number; }
interface Props { anchorEl: HTMLElement | null; placement: "left" | "below"; text: string; label: string; onClose: () => void; onNext?: () => void; }
const CALLOUT_WIDTH = 280; const CALLOUT_OFFSET = 16;

export default function OnboardingCallout({ anchorEl, placement, text, label, onClose, onNext }: Props) {
  const { t } = useTranslation();
  const isMobile = useIsMobile();
  const popupRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<Position | null>(null);

  useEffect(() => {
    if (!anchorEl) { setPos(null); return; }
    const recalc = () => {
      const rect = anchorEl!.getBoundingClientRect();
      const eff = isMobile ? "below" : placement;
      if (eff === "left") setPos({ top: rect.top, left: rect.left - CALLOUT_WIDTH - CALLOUT_OFFSET });
      else setPos({ top: rect.bottom + CALLOUT_OFFSET, left: rect.left + rect.width / 2 - CALLOUT_WIDTH / 2 });
    };
    recalc(); window.addEventListener("resize", recalc);
    const sa = findScrollAncestor(anchorEl); if (sa) sa.addEventListener("scroll", recalc);
    return () => { window.removeEventListener("resize", recalc); if (sa) sa.removeEventListener("scroll", recalc); };
  }, [anchorEl, placement, isMobile]);

  useEffect(() => {
    const h = (e: MouseEvent) => { if (popupRef.current?.contains(e.target as Node)) return; if (anchorEl?.contains(e.target as Node)) return; onClose(); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [anchorEl, onClose]);

  if (!anchorEl || !pos) return null;
  const eff = isMobile ? "below" : placement;

  return createPortal(
    // eslint-disable-next-line no-restricted-syntax -- portal position from measured DOM rect
    <div ref={popupRef} style={{ position: "fixed", top: Math.max(pos.top, 8), left: Math.max(pos.left, 8), width: CALLOUT_WIDTH, zIndex: 10000 }}>
      {eff === "left" ? <><div className={styles.tailOuterLeft} /><div className={styles.tailInnerLeft} /></> : <><div className={styles.tailOuterBelow} /><div className={styles.tailInnerBelow} /></>}
      <div className={styles.body}>
        <div className={styles.label}>{label}</div>
        <div className={styles.text}>{text}</div>
        <div className={styles.btnRow}>
          {onNext && <Button size="sm" variant="primary" onClick={onNext}>{t("onboarding_tour.next")}</Button>}
          <Button size="sm" variant="outline-secondary" onClick={onClose}>{t("onboarding_tour.close")}</Button>
        </div>
      </div>
    </div>, document.body);
}

function findScrollAncestor(el: HTMLElement): HTMLElement | null {
  let c: HTMLElement | null = el.parentElement;
  while (c) { const s = window.getComputedStyle(c); if (/(auto|scroll)/.test(s.overflow + s.overflowY)) return c; c = c.parentElement; }
  return null;
}
