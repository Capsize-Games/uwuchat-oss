import type { ChatPanel } from "../types";
import LucideIcon from "../../shared/LucideIcon";
import PanelIconBtn from "../shared/PanelIconBtn";
import styles from "./ChatDocsRow.module.css";

interface ChatDocsRowProps {
  openPanel: ChatPanel;
  togglePanel: (panel: NonNullable<ChatPanel>) => void;
  docCount: number;
}

export default function ChatDocsRow({
  openPanel,
  togglePanel,
  docCount,
}: ChatDocsRowProps) {
  return (
    <div className={`d-flex align-items-center flex-shrink-0 border-t-subtle ${styles.root}`}>
      <button
        type="button"
        onClick={() => togglePanel("knowledge")}
        title="Knowledge base"
        className={`${styles.knowledgeBtn} ${openPanel === "knowledge" ? styles.knowledgeBtnActive : styles.knowledgeBtnInactive}`}
      >
        <LucideIcon name="book" size={12} />
        <span>
          {docCount} Active document{docCount !== 1 ? "s" : ""}
        </span>
      </button>

      <span className="flex-grow-1" />

      <PanelIconBtn
        icon="history"
        title="Chat history"
        active={openPanel === "history"}
        onClick={() => togglePanel("history")}
      />
    </div>
  );
}
