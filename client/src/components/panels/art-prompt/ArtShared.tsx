import React from "react";
import shared from "./ArtShared.module.css";

const ART_PROMPT_CSS = `
  .art-no-spin::-webkit-inner-spin-button,
  .art-no-spin::-webkit-outer-spin-button { -webkit-appearance: none; margin: 0; }
  .art-no-spin { -moz-appearance: textfield; appearance: textfield; }
  .art-slider { -webkit-appearance: none; appearance: none; }
  .art-slider::-webkit-slider-thumb {
    -webkit-appearance: none; appearance: none;
    width: 10px; height: 10px; border-radius: 50%;
    background: var(--bs-primary); cursor: pointer; margin-top: -3.5px;
  }
  .art-slider::-moz-range-thumb {
    width: 10px; height: 10px; border-radius: 50%;
    background: var(--bs-primary); cursor: pointer; border: none;
  }
  .art-progress-track { position: relative; overflow: hidden; }
  .art-progress-fill { height: 100%; border-radius: inherit; background: var(--bs-info); }
  .art-progress-fill--determinate { transition: width 0.2s linear; }
  .art-progress-fill--indeterminate { position: absolute; top: 0; left: 0; width: 40%; border-radius: inherit; animation: art-progress-indeterminate 1.1s ease-in-out infinite; }
  @keyframes art-progress-indeterminate { 0% { left: -40%; } 100% { left: 100%; } }
`;

if (typeof document !== "undefined") {
  const id = "art-prompt-styles";
  if (!document.getElementById(id)) { const el = document.createElement("style"); el.id = id; el.textContent = ART_PROMPT_CSS; document.head.appendChild(el); }
}

export type ArtPopup = "settings" | "promptSettings" | "modelOptions" | null;
export type ArtPanel = "lora" | "embeddings" | "savedPrompts" | null;

export interface ArtSettingsData {
  steps: number; cfgScale: number; nSamples: number; imagesPerBatch: number;
  onStepsChange: (v: number) => void; onCfgScaleChange: (v: number) => void;
  onNSamplesChange: (v: number) => void; onImagesPerBatchChange: (v: number) => void;
}

export function Divider() { return <span className={shared.divider} />; }

export function PromptDivider({ label }: { label: string }) {
  return <div className={shared.promptDivider}><span className={shared.promptDividerLabel}>{label}</span></div>;
}

export function ToolbarIconBtn({
  title, onClick, disabled, active, badge, children,
}: { title: string; onClick?: () => void; disabled?: boolean; active?: boolean; badge?: number; children: React.ReactNode; }) {
  const cls = disabled ? shared.toolbarBtnDisabled : active ? shared.toolbarBtnActive : shared.toolbarBtnInactive;
  return (
    <button type="button" title={title} onClick={onClick} disabled={disabled} className={cls}>
      {children}
      {badge !== undefined && <span className={shared.toolbarBtnBadge} />}
    </button>
  );
}

export function CompactSlider({
  label, value, min, max, step, float, onChange,
}: { label: string; value: number; min: number; max: number; step: number; float?: boolean; onChange: (v: number) => void; }) {
  return (
    <div className={shared.compactSlider}>
      <span className={shared.compactSliderLabel}>{label}</span>
      <div className={shared.compactSliderTrack}>
        <input type="range" className={`art-slider ${shared.compactSliderRange}`} min={min} max={max} step={step} value={value} onChange={(e) => onChange(float ? parseFloat(e.target.value) : parseInt(e.target.value, 10))} />
      </div>
      <span className={shared.compactSliderValue}>{float ? value.toFixed(1) : value}</span>
    </div>
  );
}
