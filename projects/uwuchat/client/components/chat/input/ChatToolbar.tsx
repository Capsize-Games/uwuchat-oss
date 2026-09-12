interface ChatToolbarProps { streaming: boolean; input: string; handleSend: () => Promise<void>; handleCancel: () => void; }
import styles from "./ChatToolbar.module.css";

export default function ChatToolbar({ streaming, input, handleSend, handleCancel }: ChatToolbarProps) {
  return (
    <div className={`d-flex align-items-center flex-shrink-0 border-t-subtle ${styles.toolbar}`}>
      <span className={styles.spacer}>
        {streaming ? (
          <button type="button" onClick={handleCancel} title="Cancel" className={styles.cancelBtn}>
            <span className={styles.btnIcon}>✕</span>
          </button>
        ) : (
          <button type="button" onClick={handleSend} onMouseDown={(e) => e.preventDefault()}
            disabled={!input.trim()} title="Send message"
            className={input.trim() ? styles.sendActive : styles.sendDisabled}>
            <span className={styles.btnIcon}>↑</span>
          </button>
        )}
      </span>
    </div>
  );
}
