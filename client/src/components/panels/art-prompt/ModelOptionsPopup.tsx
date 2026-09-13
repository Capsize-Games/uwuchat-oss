import { createPortal } from "react-dom";
import LucideIcon from "../../shared/LucideIcon";
import { ArtDropdownPicker } from "./ArtDropdownPicker";
import type { ArtOptionsResponse } from "../../../api/client";
import styles from "./ModelOptionsPopup.module.css";
import shared from "./ArtShared.module.css";

interface ModelOptionsPopupProps {
  anchor: { left: number; bottom: number } | null;
  version: string;
  modelPath: string;
  scheduler: string;
  artOptions: ArtOptionsResponse | null;
  availableSchedulers: { label: string; value: string }[];
  onVersionChange: (v: string) => void;
  onModelChange: (m: string) => void;
  onSchedulerChange: (s: string) => void;
}

export default function ModelOptionsPopup({
  anchor,
  version,
  modelPath,
  scheduler,
  artOptions,
  availableSchedulers,
  onVersionChange,
  onModelChange,
  onSchedulerChange,
}: ModelOptionsPopupProps) {
  if (!anchor) return null;

  return createPortal(
    <div
      id="art-model-options-popup"
      className={`bg-theme-panel d-flex flex-column ${styles.popup}`}
      // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
      style={{
        left: anchor.left,
        bottom: anchor.bottom,
      }}
    >
      <div className={`${shared.sectionLabel} ${styles.headerRow}`}>
        Art Model Options
      </div>

      {/* Version */}
      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <LucideIcon name="circle-dot" size={9} />
          <span>Version</span>
        </div>
        <ArtDropdownPicker
          value={version}
          placeholder="Choose version…"
          options={
            artOptions?.versions?.map((v) => ({
              label: v.name,
              value: v.name,
            })) ?? []
          }
          onChange={onVersionChange}
        />
      </div>

      {/* Model */}
      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <LucideIcon name="circle-dot" size={9} />
          <span>Model</span>
        </div>
        <ArtDropdownPicker
          value={modelPath}
          placeholder="Choose model…"
          options={
            artOptions?.versions?.find((v) => v.name === version)?.models ?? []
          }
          onChange={onModelChange}
          disabled={!version}
        />
      </div>

      {/* Scheduler */}
      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <LucideIcon name="circle-dot" size={9} />
          <span>Scheduler</span>
        </div>
        <ArtDropdownPicker
          value={scheduler}
          placeholder="Choose scheduler…"
          options={availableSchedulers}
          onChange={onSchedulerChange}
          disabled={!version || availableSchedulers.length === 0}
        />
      </div>
    </div>,
    document.body,
  );
}
