import type { ChatPanel } from "../types";
import { KnowledgeBasePanel } from "@/components/panels/KnowledgeBasePanel";
import { ChatHistoryPanel } from "../../panels/ChatHistoryPanel";
import { ProductivityPanel } from "./ProductivityPanel";

interface ChatPopupPanelProps {
  openPanel: ChatPanel;
  popupAnchor: {
    left: number;
    bottom: number;
    width: number;
    height: number;
  } | null;
  currentChatbotId: number | null;
  onSelectChatbot?: (id: number | null) => void;
  onCreateUwu?: () => void;
  onClose: () => void;
}

export default function ChatPopupPanel({
  openPanel,
  popupAnchor,
  currentChatbotId,
  onSelectChatbot,
  onCreateUwu,
  onClose,
}: ChatPopupPanelProps) {
  if (!openPanel || !popupAnchor) return null;

  return (
    <div
      id="chat-panel-popup"
      className="bg-theme-panel d-flex flex-column overflow-hidden"
      // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
      style={{
        position: "fixed",
        left: popupAnchor.left,
        bottom: popupAnchor.bottom,
        width: Math.max(popupAnchor.width, 360),
        height: popupAnchor.height,
        zIndex: 1300,
        border: "1px solid rgba(255,255,255,0.14)",
        borderRadius: 0,
        boxShadow: "4px -4px 24px rgba(0,0,0,0.7)",
      }}
    >
      {openPanel === "knowledge" && <KnowledgeBasePanel />}
      {openPanel === "uwu-selector" && (
        <ChatHistoryPanel
          currentChatbotId={currentChatbotId}
          onSelectUwu={(id) => {
            onSelectChatbot?.(id);
            onClose();
          }}
          onCreateUwu={onCreateUwu ? () => { onCreateUwu(); onClose(); } : undefined}
          onUnfriendChatbot={() => {
            onSelectChatbot?.(null);
          }}
        />
      )}
      {openPanel === "productivity" && (
        <ProductivityPanel chatbotId={currentChatbotId} />
      )}
    </div>
  );
}
