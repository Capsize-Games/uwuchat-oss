import { useState } from "react";
import Spinner from "react-bootstrap/Spinner";
import LucideIcon from "../shared/LucideIcon";
import { useConversations } from "../../hooks/useConversations";
import styles from "./ChatHistoryPanel.module.css";

/**
 * Format an ISO-8601 timestamp for the conversation list.
 * Shows relative labels for today/yesterday and a compact date otherwise.
 */
function formatConversationDate(iso: string | undefined): string {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return "";

    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const yesterday = new Date(today.getTime() - 86_400_000);
    const target = new Date(d.getFullYear(), d.getMonth(), d.getDate());

    const time = d.toLocaleTimeString(undefined, {
      hour: "numeric",
      minute: "2-digit",
    });

    if (target.getTime() === today.getTime()) {
      return `Today ${time}`;
    }
    if (target.getTime() === yesterday.getTime()) {
      return `Yesterday ${time}`;
    }

    const dateStr = d.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
    });
    const yearStr =
      d.getFullYear() !== now.getFullYear()
        ? `, ${d.getFullYear()}`
        : "";
    return `${dateStr}${yearStr}, ${time}`;
  } catch {
    return "";
  }
}

export function ChatHistoryPanel({
  onSelectConversation,
}: {
  onSelectConversation: (id: number) => void;
}) {
  const { conversations, loading, remove } = useConversations();
  const [confirmDeleteAll, setConfirmDeleteAll] = useState(false);

  const handleDeleteAll = () => {
    conversations.forEach((c) => remove(c.id));
    setConfirmDeleteAll(false);
  };

  return (
    <div className="d-flex flex-column h-100">
      {/* Sticky header */}
      <div
        className={`flex-shrink-0 d-flex align-items-center justify-content-between bg-theme-panel border-b-theme ${styles.header}`}
      >
        <span className="text-panel-label text-uppercase">
          Chat History
        </span>

        {confirmDeleteAll ? (
          <div className={`d-flex align-items-center ${styles.confirmRow}`}>
            <span className={`text-theme-secondary ${styles.confirmText}`}>
              Delete all?
            </span>
            <button type="button" onClick={handleDeleteAll} className={styles.confirmBtn}>
              Yes
            </button>
            <button type="button" onClick={() => setConfirmDeleteAll(false)} className={styles.confirmCancelBtn}>
              No
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setConfirmDeleteAll(true)}
            disabled={conversations.length === 0}
            className={conversations.length === 0 ? styles.deleteAllBtnDisabled : styles.deleteAllBtnEnabled}
          >
            <LucideIcon name="trash-2" size={11} />
            Delete All
          </button>
        )}
      </div>

      {/* Scrollable list */}
      <div className="scroll-panel">
        {loading ? (
          <div className="p-3 text-center">
            <Spinner animation="border" size="sm" />
          </div>
        ) : conversations.length === 0 ? (
          <p className="text-muted small p-2">
            No conversations yet. Start a chat to create one.
          </p>
        ) : (
          conversations.map((c) => (
            <div
              key={c.id}
              onClick={() => onSelectConversation(c.id)}
              className={c.current ? styles.rowCurrent : styles.row}
            >
              <div className={styles.rowBody}>
                <span className={c.current ? styles.rowTitleCurrent : styles.rowTitleDefault}>
                  {c.first_user_message
                    ? c.first_user_message.length > 56
                      ? `${c.first_user_message.slice(0, 56)}…`
                      : c.first_user_message
                    : c.title || `Chat #${c.id}`}
                </span>
                <span className={styles.rowDate}>
                  {formatConversationDate(c.created_at)}
                </span>
              </div>
              <button
                type="button"
                title="Delete conversation"
                onClick={(e) => {
                  e.stopPropagation();
                  remove(c.id);
                }}
                className={styles.deleteBtn}
              >
                <LucideIcon name="trash-2" size={12} />
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
