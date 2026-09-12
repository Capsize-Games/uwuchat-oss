import type { ArtPanel } from "./ArtShared";
import LoraPanel from "../LoraPanel";
import EmbeddingsPanel from "../EmbeddingsPanel";
import SavedPromptsPanel from "./SavedPromptsModal";
import type { SavedPrompt } from "../../../api/art";
import styles from "./ArtPanelPopup.module.css";

interface ArtPanelPopupProps {
  openPanel: ArtPanel;
  anchor: {
    left: number;
    bottom: number;
    width: number;
    height: number;
  } | null;
  version: string;
  onLoadPrompt: (p: SavedPrompt) => void;
  onCloseSavedPrompts: () => void;
}

export default function ArtPanelPopup({
  openPanel,
  anchor,
  version,
  onLoadPrompt,
  onCloseSavedPrompts,
}: ArtPanelPopupProps) {
  if (!openPanel || !anchor) return null;

  return (
    <div
      id="art-panel-popup"
      className={`bg-theme-panel d-flex flex-column overflow-hidden ${styles.popup}`}
      // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
      style={{
        left: anchor.left,
        bottom: anchor.bottom,
        width: anchor.width,
        height: anchor.height,
      }}
    >
      {openPanel === "lora" && <LoraPanel />}
      {openPanel === "embeddings" && <EmbeddingsPanel />}
      {openPanel === "savedPrompts" && (
        <SavedPromptsPanel
          version={version}
          onLoad={onLoadPrompt}
          onClose={onCloseSavedPrompts}
        />
      )}
    </div>
  );
}
