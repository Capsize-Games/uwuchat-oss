import { Fragment, useState, useEffect } from "react";
import { Alert } from "react-bootstrap";
import { PromptTextareas } from "./art-prompt/PromptTextareas";
import { PromptControls } from "./art-prompt/PromptControls";
import { useArtPromptState } from "./art-prompt/useArtPromptState";
import { useArtOverlays } from "./art-prompt/useArtOverlays";
import GenerationInfoPanel from "./art-prompt/GenerationInfoPanel";
import InfoDropdownPopup from "./art-prompt/InfoDropdownPopup";
import ArtPanelPopup from "./art-prompt/ArtPanelPopup";
import PromptSettingsPopup from "./art-prompt/PromptSettingsPopup";
import { saveToStorage } from "./art-model/ArtModelStorage";
import SourceImagePanel from "./art-prompt/SourceImagePanel";
import SizePopup from "./art-prompt/SizePopup";
import styles from "./ArtPromptPanel.module.css";

// side-effect: injects CSS for sliders / number spinners
import "./art-prompt/ArtShared";

export default function ArtPromptPanel({
  visible = true,
  generationType: externalGenerationType,
  onGenerationTypeChange: externalOnGenerationTypeChange,
}: {
  visible?: boolean;
  generationType?: "txt2img" | "img2img" | "inpaint";
  onGenerationTypeChange?: (v: "txt2img" | "img2img" | "inpaint") => void;
}) {
  const s = useArtPromptState({ generationType: externalGenerationType });
  const o = useArtOverlays();

  // Use external generationType props when provided (e.g. from CanvasPanel),
  // otherwise fall back to the internal state from useArtPromptState.
  const genType = externalGenerationType ?? s.generationType;
  const onGenTypeChange = externalOnGenerationTypeChange ?? s.setGenerationType;

  const [showInfo, setShowInfo] = useState(() => {
    try {
      return (
        localStorage.getItem("airunner_show_gen_info") !== "false"
      );
    } catch {
      return true;
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem("airunner_show_gen_info", String(showInfo));
    } catch {}
  }, [showInfo]);

  if (!visible) return null;

  return (
    <Fragment>
      <div className="flex-grow-1 d-flex flex-column overflow-hidden w-100">
        <div className="d-flex flex-column flex-grow-1 overflow-hidden">
          <div
            className={`flex-grow-1 d-flex flex-column bg-theme-panel overflow-hidden min-h-0 ${styles.panel}`}
          >

            <PromptTextareas
              prompt={s.prompt}
              secondaryPrompt={s.secondaryPrompt}
              negativePrompt={s.negativePrompt}
              secondaryNegativePrompt={s.secondaryNegativePrompt}
              isMultiPrompt={s.isMultiPrompt}
              generating={s.generating}
              onPromptChange={(v) => {
                s.setPrompt(v);
                s.persist({ prompt: v });
              }}
              onSecondaryPromptChange={(v) => {
                s.setSecondaryPrompt(v);
                s.persist({ secondary_prompt: v });
              }}
              onNegativePromptChange={(v) => {
                s.setNegativePrompt(v);
                s.persist({ negative_prompt: v });
              }}
              onSecondaryNegativePromptChange={(v) => {
                s.setSecondaryNegativePrompt(v);
                s.persist({ secondary_negative_prompt: v });
              }}
            />

            {/* ── Source image panel (img2img / inpaint) ─────────────
             * Shown only when generation type is img2img or inpaint. */}
            {(genType === "img2img" || genType === "inpaint") && (
              <SourceImagePanel
                generationType={genType}
                strength={s.strength}
                onStrengthChange={s.setStrength}
                feather={s.feather}
                onFeatherChange={s.setFeather}
              />
            )}

            <GenerationInfoPanel
              showInfo={showInfo}
              onToggleShowInfo={() => setShowInfo((v) => !v)}
              version={s.version}
              modelPath={s.modelPath}
              scheduler={s.scheduler}
              steps={s.steps}
              cfgScale={s.cfgScale}
              nSamples={s.nSamples}
              imagesPerBatch={s.imagesPerBatch}
              generationType={genType}
              seed={s.seed}
              seedRandomized={s.seedRandomized}
              genWidth={s.genWidth}
              genHeight={s.genHeight}
              activeLoras={s.activeLoras}
              activeEmbeddings={s.activeEmbeddings}
              isMultiPrompt={s.isMultiPrompt}
              artOptions={s.artOptions}
              onVersionChange={s.handleVersion}
              onModelChange={s.handleModel}
              onSchedulerChange={s.handleScheduler}
              onStepsChange={s.setSteps}
              onCfgScaleChange={s.setCfgScale}
              onNSamplesChange={s.setNSamples}
              onImagesPerBatchChange={s.setImagesPerBatch}
              onGenerationTypeChange={onGenTypeChange}
              onSeedChange={s.handleSeedChange}
              onToggleRandom={s.handleToggleRandom}
              onGenWidthChange={s.setGenWidth}
              onGenHeightChange={s.setGenHeight}
              onToggleLoraPanel={(anchorRect) => s.togglePanel("lora", anchorRect)}
              onToggleEmbeddingsPanel={(anchorRect) =>
                s.togglePanel("embeddings", anchorRect)
              }
              persistGen={s.persistGen}
              openDropdown={o.openDropdown}
              toggleGenSize={o.toggleGenSize}
            />


            {s.errorMessage && (
              <div className={styles.errorWrap}>
                <Alert
                  variant="danger"
                  dismissible
                  className={styles.alert}
                  onClose={() => s.setErrorMessage(null)}
                >
                  {s.errorMessage}
                </Alert>
              </div>
            )}

            <div
              ref={s.toolbarRef}
              className="flex-shrink-0 d-flex flex-column"
            >
              <PromptControls
                ref={s.controlsRef}
                generating={s.generating}
                progress={s.progress}
                phase={s.phase}
                hasPrompt={!!s.prompt.trim()}
                saving={s.saving}
                promptPopupOpen={
                  s.openPopup === "promptSettings"
                }
                promptBtnRef={s.promptBtnRef}
                activeLoras={s.activeLoras}
                activeEmbeddings={s.activeEmbeddings}
                isMultiPrompt={s.isMultiPrompt}
                loraPanelOpen={s.openPanel === "lora"}
                embeddingsPanelOpen={
                  s.openPanel === "embeddings"
                }
                seedRandomized={s.seedRandomized}
                onClear={s.handleClearPrompts}
                onSave={s.handleSavePrompt}
                onToggleSavedPrompts={() =>
                  s.togglePanel("savedPrompts")
                }
                onTogglePromptPopup={() =>
                  s.togglePopup("promptSettings")
                }
                onToggleLora={() => s.togglePanel("lora")}
                onToggleEmbeddings={() =>
                  s.togglePanel("embeddings")
                }
                onToggleRandom={s.handleToggleRandom}
                onGenerate={s.onGenerate}
                onCancel={s.onCancel}
              />
            </div>
          </div>
        </div>
      </div>

      <InfoDropdownPopup
        field={o.dropdownField}
        anchor={o.dropdownAnchor}
        version={s.version}
        modelPath={s.modelPath}
        scheduler={s.scheduler}
        generationType={genType}
        artOptions={s.artOptions}
        availableSchedulers={s.availableSchedulers}
        onSelectVersion={s.handleVersion}
        onSelectModel={s.handleModel}
        onSelectScheduler={s.handleScheduler}
        onSelectGenType={onGenTypeChange}
        onClose={o.closeDropdown}
      />

      <ArtPanelPopup
        openPanel={s.openPanel}
        anchor={s.artPanelAnchor}
        version={s.version}
        onLoadPrompt={s.handleLoadPrompt}
        onCloseSavedPrompts={() =>
          s.togglePanel("savedPrompts")
        }
      />

      {/* ── Prompt settings popup ──────────────────────── */}
      <PromptSettingsPopup
        anchor={
          s.openPopup === "promptSettings"
            ? s.promptSettingsAnchor
            : null
        }
        saving={s.saving}
        promptEmpty={!s.prompt.trim()}
        onNewPrompt={() => {
          s.handleClearPrompts();
          s.togglePopup("promptSettings");
        }}
        onSavePrompt={() => {
          s.handleSavePrompt();
          s.togglePopup("promptSettings");
        }}
        onLoadSavedPrompts={() => {
          s.togglePanel("savedPrompts");
          s.togglePopup("promptSettings");
        }}
      />
      {o.showGenSize && (
        <SizePopup
          anchor={o.genSizeAnchor}
          portalId={o.genSizePortalId}
          genWidth={s.genWidth}
          genHeight={s.genHeight}
          onWidthChange={(v) => { s.setGenWidth(v); saveToStorage("gen_width", v); s.persistGen({ width: v }); }}
          onHeightChange={(v) => { s.setGenHeight(v); saveToStorage("gen_height", v); s.persistGen({ height: v }); }}
          persistGen={s.persistGen}
        />
      )}
    </Fragment>
  );
}
