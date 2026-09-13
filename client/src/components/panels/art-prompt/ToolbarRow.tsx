import type { RefObject } from "react";
import { createPortal } from "react-dom";
import { saveToStorage } from "../art-model/ArtModelStorage";
import LucideIcon from "../../shared/LucideIcon";
import { ToolbarIconBtn } from "./ArtShared";
import { SettingsPopup } from "./SettingsPopup";
import ModelOptionsPopup from "./ModelOptionsPopup";
import PromptSettingsPopup from "./PromptSettingsPopup";
import GenTypeButton from "./GenTypeButton";
import SizeButton from "./SizeButton";
import type { ArtOptionsResponse } from "../../../api/client";
import styles from "./ToolbarRow.module.css";

interface ToolbarRowProps {
  version: string;
  modelPath: string;
  scheduler: string;
  artOptions: ArtOptionsResponse | null;
  availableSchedulers: { label: string; value: string }[];
  activeLoras: { id: number; name: string }[];
  activeEmbeddings: { id: number; name: string }[];
  isMultiPrompt: boolean;
  seedRandomized: boolean;
  saving: boolean;
  steps: number;
  cfgScale: number;
  nSamples: number;
  imagesPerBatch: number;
  genWidth: number;
  genHeight: number;
  generationType: "txt2img" | "img2img";
  openPopup: string | null;
  openPanel: string | null;
  settingsAnchor: { left: number; bottom: number } | null;
  promptSettingsAnchor: { left: number; bottom: number } | null;
  settingsBtnRef: RefObject<HTMLDivElement | null>;
  prompt: string;
  onVersionChange: (v: string) => void;
  onModelChange: (m: string) => void;
  onSchedulerChange: (s: string) => void;
  onToggleRandom: () => void;
  onTogglePanel: (p: string) => void;
  onTogglePopup: (p: string) => void;
  onClearPrompts: () => void;
  onSavePrompt: () => void;
  onSetGenerationType: (v: "txt2img" | "img2img") => void;
  onWidthChange: (v: number) => void;
  onHeightChange: (v: number) => void;
  onStepsChange: (v: number) => void;
  onCfgScaleChange: (v: number) => void;
  onNSamplesChange: (v: number) => void;
  onImagesPerBatchChange: (v: number) => void;
  persistGen: (u: Record<string, unknown>) => void;
  showModelOptions: boolean;
  modelOptionsBtnRef: RefObject<HTMLDivElement | null>;
  modelOptionsAnchor: { left: number; bottom: number } | null;
  showSize: boolean;
  sizeBtnRef: RefObject<HTMLDivElement | null>;
  sizeAnchor: { left: number; bottom: number } | null;
  showGenType: boolean;
  genTypeBtnRef: RefObject<HTMLDivElement | null>;
  genTypeAnchor: { left: number; bottom: number } | null;
  sizePortalId: string;
  toggleModelOptions: () => void;
  toggleSize: () => void;
  toggleGenType: () => void;
  closeGenType: () => void;
}

export default function ToolbarRow(props: ToolbarRowProps) {
  const {
    version, modelPath, scheduler, artOptions, availableSchedulers,
    activeLoras, activeEmbeddings, isMultiPrompt, seedRandomized,
    saving, steps, cfgScale, nSamples, imagesPerBatch, genWidth,
    genHeight, generationType, openPopup, openPanel, settingsAnchor,
    promptSettingsAnchor, settingsBtnRef, prompt,
    onVersionChange, onModelChange, onSchedulerChange,
    onToggleRandom, onTogglePanel, onTogglePopup, onClearPrompts,
    onSavePrompt, onSetGenerationType, onWidthChange, onHeightChange,
    onStepsChange, onCfgScaleChange, onNSamplesChange,
    onImagesPerBatchChange, persistGen,
    showModelOptions, modelOptionsBtnRef, modelOptionsAnchor,
    showSize, sizeBtnRef, sizeAnchor, showGenType, genTypeBtnRef,
    genTypeAnchor, sizePortalId, toggleModelOptions, toggleSize,
    toggleGenType, closeGenType,
  } = props;

  return (
    <div className={styles.row}>
      <div ref={modelOptionsBtnRef}>
        <ToolbarIconBtn
          title="Art model options"
          onClick={toggleModelOptions}
          active={showModelOptions}
        >
          <LucideIcon name="sparkles" size={14} />
        </ToolbarIconBtn>
      </div>

      <ModelOptionsPopup
        anchor={showModelOptions ? modelOptionsAnchor : null}
        version={version}
        modelPath={modelPath}
        scheduler={scheduler}
        artOptions={artOptions}
        availableSchedulers={availableSchedulers}
        onVersionChange={onVersionChange}
        onModelChange={onModelChange}
        onSchedulerChange={onSchedulerChange}
      />

      <ToolbarIconBtn
        title={isMultiPrompt
          ? `Embeddings${activeEmbeddings.length > 0 ? ` (${activeEmbeddings.length})` : ""}`
          : "Embeddings unavailable for Z-Image"}
        onClick={() => onTogglePanel("embeddings")}
        active={openPanel === "embeddings"}
        badge={activeEmbeddings.length > 0 ? activeEmbeddings.length : undefined}
        disabled={!isMultiPrompt}
      >
        <LucideIcon name="scan-text" size={14} />
      </ToolbarIconBtn>

      <ToolbarIconBtn
        title={`LoRA${activeLoras.length > 0 ? ` (${activeLoras.length})` : ""}`}
        onClick={() => onTogglePanel("lora")}
        active={openPanel === "lora"}
        badge={activeLoras.length > 0 ? activeLoras.length : undefined}
      >
        <LucideIcon name="puzzle" size={14} />
      </ToolbarIconBtn>

      <div ref={settingsBtnRef}>
        <ToolbarIconBtn
          title="Generation settings"
          onClick={() => onTogglePopup("settings")}
          active={openPopup === "settings"}
        >
          <LucideIcon name="settings-2" size={14} />
        </ToolbarIconBtn>
      </div>

      <ToolbarIconBtn
        title={seedRandomized ? "Seed: switch to fixed" : "Seed: switch to random"}
        onClick={onToggleRandom}
        active={seedRandomized}
      >
        <LucideIcon name="shuffle" size={14} />
      </ToolbarIconBtn>

      {openPopup === "settings" && settingsAnchor && createPortal(
        <div
          id="art-settings-popup"
          className={`bg-theme-panel overflow-y-auto ${styles.settingsPopup}`}
          // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
          style={{
            left: settingsAnchor.left,
            bottom: settingsAnchor.bottom,
          }}
        >
          <SettingsPopup
            steps={steps} cfgScale={cfgScale}
            nSamples={nSamples} imagesPerBatch={imagesPerBatch}
            onStepsChange={(v) => { onStepsChange(v); saveToStorage("steps", v); persistGen({ steps: v }); }}
            onCfgScaleChange={(v) => { onCfgScaleChange(v); saveToStorage("cfg_scale", v); persistGen({ cfg_scale: v }); }}
            onNSamplesChange={(v) => { onNSamplesChange(v); saveToStorage("n_samples", v); persistGen({ n_samples: v }); }}
            onImagesPerBatchChange={(v) => { onImagesPerBatchChange(v); saveToStorage("images_per_batch", v); persistGen({ images_per_batch: v }); }}
          />
        </div>,
        document.body,
      )}

      <PromptSettingsPopup
        anchor={openPopup === "promptSettings" ? promptSettingsAnchor : null}
        saving={saving}
        promptEmpty={!prompt.trim()}
        onNewPrompt={() => { onClearPrompts(); onTogglePopup("promptSettings"); }}
        onSavePrompt={() => { onSavePrompt(); onTogglePopup("promptSettings"); }}
        onLoadSavedPrompts={() => { onTogglePanel("savedPrompts"); onTogglePopup("promptSettings"); }}
      />

      <span className="flex-grow-1" />

      <GenTypeButton
        genTypeBtnRef={genTypeBtnRef}
        showGenType={showGenType}
        toggleGenType={toggleGenType}
        genTypeAnchor={genTypeAnchor}
        generationType={generationType}
        onSetGenerationType={onSetGenerationType}
        closeGenType={closeGenType}
      />

      <SizeButton
        sizeBtnRef={sizeBtnRef}
        showSize={showSize}
        toggleSize={toggleSize}
        sizeAnchor={sizeAnchor}
        sizePortalId={sizePortalId}
        genWidth={genWidth}
        genHeight={genHeight}
        onWidthChange={onWidthChange}
        onHeightChange={onHeightChange}
        persistGen={persistGen}
      />
    </div>
  );
}
