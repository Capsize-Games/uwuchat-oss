import { forwardRef, type RefObject } from "react";
import LucideIcon from "../../shared/LucideIcon";
import { ToolbarIconBtn } from "./ArtShared";
import styles from "./PromptControls.module.css";

type Phase = "idle" | "loading" | "completed" | "cancelled" | "failed";

interface Props {
  generating: boolean;
  progress: number;
  phase: Phase;
  hasPrompt: boolean;
  saving: boolean;
  promptPopupOpen: boolean;
  promptBtnRef: RefObject<HTMLDivElement | null>;
  activeLoras: { id: number; name: string }[];
  activeEmbeddings: { id: number; name: string }[];
  isMultiPrompt: boolean;
  loraPanelOpen: boolean;
  embeddingsPanelOpen: boolean;
  seedRandomized: boolean;
  onClear: () => void;
  onSave: () => void;
  onToggleSavedPrompts: () => void;
  onTogglePromptPopup: () => void;
  onToggleLora: () => void;
  onToggleEmbeddings: () => void;
  onToggleRandom: () => void;
  onGenerate: () => void;
  onCancel: () => void;
}

function generateBg(phase: Phase, hasPrompt: boolean): string {
  if (phase === "completed") return "var(--bs-success)";
  if (phase === "failed" || phase === "cancelled") return "var(--bs-danger)";
  return hasPrompt ? "var(--bs-primary)" : "rgba(255,255,255,0.1)";
}

export const PromptControls = forwardRef<HTMLDivElement, Props>(function PromptControls({
  generating, progress, phase, hasPrompt, saving,
  promptPopupOpen, promptBtnRef,
  activeLoras, activeEmbeddings, isMultiPrompt,
  loraPanelOpen, embeddingsPanelOpen, seedRandomized,
  onClear, onSave, onToggleSavedPrompts, onTogglePromptPopup,
  onToggleLora, onToggleEmbeddings, onToggleRandom,
  onGenerate, onCancel,
}, ref) {
  return (
    <div ref={ref} className={styles.bar}>
      {/* Left: prompt settings popup trigger */}
      <div ref={promptBtnRef}>
        <ToolbarIconBtn
          title="Prompt settings"
          onClick={onTogglePromptPopup}
          active={promptPopupOpen}
        >
          <LucideIcon name="message-square" size={15} />
        </ToolbarIconBtn>
      </div>

      {/* Center: progress bar */}
      <div className={`flex-grow-1 ${styles.progressWrap}`}>
        {(() => {
          const active = phase === "loading" || generating;
          const indeterminate = active && progress === 0;
          return (
            <div className={`art-progress-track ${styles.progressTrack}`}>
              {indeterminate ? (
                <div className="art-progress-fill art-progress-fill--indeterminate" />
              ) : (
                <div
                  className="art-progress-fill art-progress-fill--determinate"
                  // eslint-disable-next-line no-restricted-syntax -- computed dimension from state/prop
                  style={{ width: active ? `${progress}%` : "0%" }}
                />
              )}
            </div>
          );
        })()}
      </div>

      {/* Right: generate / cancel */}
      {generating ? (
        <button type="button" onClick={onCancel}
          title={progress > 0 ? `${progress}% — click to cancel` : "Cancel"}
          className={styles.cancelBtn}
        >
          <LucideIcon name="circle-stop" size={13} />
        </button>
      ) : (
        <button
          type="button" onClick={onGenerate} disabled={!hasPrompt}
          title="Generate image"
          className={hasPrompt ? styles.generateBtn : styles.generateBtnDisabled}
          style={hasPrompt ? { background: generateBg(phase, hasPrompt) } : undefined}
        >
          <LucideIcon name="chevron-up" size={13} />
        </button>
      )}
    </div>
  );
});
