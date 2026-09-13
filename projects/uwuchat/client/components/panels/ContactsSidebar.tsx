import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import Spinner from "react-bootstrap/Spinner";
import LucideIcon from "@/components/shared/LucideIcon";
import { ChatHistoryPanel } from "./ChatHistoryPanel";
import styles from "./ContactsSidebar.module.css";

interface ContactsSidebarProps {
  currentChatbotId: number | null;
  onSelectUwu: (id: number) => void;
  onUnfriendChatbot: (id: number) => void;
  onCreateUwu?: () => void;
  /** True while connectRandom is creating a random chatbot. */
  connecting?: boolean;
  /** Translated error from connectRandom (e.g. quota exceeded). */
  connectError?: string | null;
  onCloseMobile: () => void;
  /** "fullPage" swaps in as the main content area; "sidebar" is a fixed overlay. */
  variant?: "sidebar" | "fullPage";
}

/**
 * Contacts list — content-only component. The header (logo, contacts
 * toggle, account menu) is rendered by the parent right-panel chrome.
 */
export function ContactsSidebar({
  currentChatbotId,
  onSelectUwu,
  onUnfriendChatbot,
  onCreateUwu,
  connecting,
  connectError,
  onCloseMobile,
  variant,
}: ContactsSidebarProps) {
  const isFullPage = variant === "fullPage";
  const { t } = useTranslation();

  const handleSelect = (id: number) => {
    onSelectUwu(id);
  };

  const handleCreateUwu = useCallback(() => {
    onCreateUwu?.();
  }, [onCreateUwu]);

  return (
    <div
      className={isFullPage ? "" : "contacts-mobile-open"}
      style={isFullPage
        ? {
            display: "flex",
            flexDirection: "column",
            height: "100%",
          }
        : {
            position: "fixed",
            inset: 0,
            zIndex: 1400,
            background: "var(--theme-panel-bg, #1a1a2e)",
            display: "none",
            flexDirection: "column",
          }
      }
    >
      <ChatHistoryPanel
        currentChatbotId={currentChatbotId}
        onSelectUwu={handleSelect}
        onUnfriendChatbot={onUnfriendChatbot}
        onClose={onCloseMobile}
      />

      {/* "+ New contact" — anchored at the bottom, always visible */}
      <div className={styles.bottomBar}>
        <button
          type="button"
          className="new-contact-btn"
          onClick={handleCreateUwu}
          disabled={connecting}
        >
          {connecting
            ? <Spinner animation="border" size="sm" />
            : <LucideIcon name="user-plus" size={16} />}
          {connecting
            ? t("sidebar.generating_character")
            : t("sidebar.new_contact")}
        </button>
        {connectError && (
          <div className={styles.connectError}>{connectError}</div>
        )}
      </div>
    </div>
  );
}
