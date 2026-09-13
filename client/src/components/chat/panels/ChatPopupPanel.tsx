import type { ChatPanel } from "../types";
import { KnowledgeBasePanel } from "../../panels/KnowledgeBasePanel";
import { ChatHistoryPanel } from "../../panels/ChatHistoryPanel";
import styles from "./ChatPopupPanel.module.css";

interface ChatPopupPanelProps {
  openPanel: ChatPanel;
  popupAnchor: {
    left: number;
    bottom: number;
    width: number;
    height: number;
  } | null;
  onSelectConversation?: (id: number) => void;
  onClose: () => void;
}

export default function ChatPopupPanel({
  openPanel,
  popupAnchor,
  onSelectConversation,
  onClose,
}: ChatPopupPanelProps) {
  if (!openPanel || !popupAnchor) return null;

  return (
    <div
      id="chat-panel-popup"
      className={`bg-theme-panel d-flex flex-column overflow-hidden ${styles.popup}`}
      // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
      style={{
        left: popupAnchor.left,
        bottom: popupAnchor.bottom,
        width: Math.max(popupAnchor.width, 360),
        height: popupAnchor.height,
      }}
    >
      {openPanel === "knowledge" && <KnowledgeBasePanel />}
      {openPanel === "history" && (
        <ChatHistoryPanel
          onSelectConversation={(id) => {
            onSelectConversation?.(id);
            onClose();
          }}
        />
      )}
    </div>
  );
}
