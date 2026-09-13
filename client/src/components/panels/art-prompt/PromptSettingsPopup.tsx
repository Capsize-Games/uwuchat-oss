import { createPortal } from "react-dom";
import LucideIcon from "../../shared/LucideIcon";
import styles from "./PromptSettingsPopup.module.css";

interface PromptSettingsPopupProps {
  anchor: { left: number; bottom: number } | null;
  saving: boolean;
  promptEmpty: boolean;
  onNewPrompt: () => void;
  onSavePrompt: () => void;
  onLoadSavedPrompts: () => void;
}

export default function PromptSettingsPopup({
  anchor,
  saving,
  promptEmpty,
  onNewPrompt,
  onSavePrompt,
  onLoadSavedPrompts,
}: PromptSettingsPopupProps) {
  if (!anchor) return null;

  return createPortal(
    <div
      id="art-prompt-settings-popup"
      className={`bg-theme-panel ${styles.popup}`}
      // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
      style={{
        left: anchor.left,
        bottom: anchor.bottom,
      }}
      onMouseDown={(e) => e.stopPropagation()}
    >
      {/* New Prompt */}
      <button type="button" onClick={onNewPrompt} className={styles.menuBtn}>
        <LucideIcon name="message-square-plus" size={14} />
        <span>New Prompt</span>
      </button>

      {/* Save Prompt */}
      <button
        type="button"
        onClick={onSavePrompt}
        disabled={saving || promptEmpty}
        className={saving || promptEmpty ? styles.menuBtnDisabled : styles.menuBtn}
      >
        <LucideIcon name={saving ? "loader" : "save"} size={14} />
        <span>Save Prompt</span>
      </button>

      {/* Load saved prompts */}
      <button type="button" onClick={onLoadSavedPrompts} className={styles.menuBtnBorder}>
        <LucideIcon name="folder-open" size={14} />
        <span>Load saved prompts</span>
      </button>
    </div>,
    document.body,
  );
}
