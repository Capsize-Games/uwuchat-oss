import ModelSelector from "../ModelSelector";
import LucideIcon from "../../shared/LucideIcon";
import ToolbarToggle from "../shared/ToolbarToggle";
import { EdgeOnly } from "../../../context/DeploymentContext";
import styles from "./ChatToolbar.module.css";

interface ChatToolbarProps {
  ttsOn: boolean;
  sttOn: boolean;
  onToggleTts?: () => void;
  onToggleStt?: () => void;
  streaming: boolean;
  input: string;
  handleSend: () => Promise<void>;
  handleCancel: () => void;
  handleNewConversation: () => Promise<void>;
}

export default function ChatToolbar({
  ttsOn,
  sttOn,
  onToggleTts,
  onToggleStt,
  streaming,
  input,
  handleSend,
  handleCancel,
  handleNewConversation,
}: ChatToolbarProps) {
  return (
    <div className={`d-flex align-items-center flex-shrink-0 border-t-subtle ${styles.root}`}>
      <button
        type="button"
        onClick={handleNewConversation}
        title="New conversation"
        className={styles.iconBtn}
      >
        <LucideIcon name="message-circle-plus" size={15} />
      </button>

      <EdgeOnly>
        <span className={styles.separator} />
        <ModelSelector />

        <ToolbarToggle
          active={ttsOn}
          title="Text to Speech"
          onClick={onToggleTts}
          icon="speaker"
        />

        <ToolbarToggle
          active={sttOn}
          title="Speech to Text"
          onClick={onToggleStt}
          icon="mic"
        />
      </EdgeOnly>

      <span className={styles.spacer}>
        {streaming ? (
          <button
            type="button"
            onClick={handleCancel}
            title="Cancel"
            className={styles.cancelBtn}
          >
            <LucideIcon name="circle-x" size={15} />
          </button>
        ) : (
          <button
            type="button"
            onClick={handleSend}
            onMouseDown={(e) => e.preventDefault()}
            disabled={!input.trim()}
            title="Send message"
            className={`${styles.sendBtn} ${input.trim() ? styles.sendBtnActive : styles.sendBtnInactive}`}
          >
            <LucideIcon name="chevron-up" size={15} />
          </button>
        )}
      </span>
    </div>
  );
}
