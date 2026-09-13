import { useState, useCallback, type MouseEvent } from "react";
import { useTranslation } from "react-i18next";
import LucideIcon from "@/components/shared/LucideIcon";
import { useAuth } from "../../../hooks/useAuth";
import ReportReasonPicker from "./ReportReasonPicker";
import styles from "./MessageActions.module.css";

interface MessageActionsProps { isUser: boolean; content: string; onDelete?: () => void; onReport?: (reason: string, detail: string) => void; }

export default function MessageActions({ isUser, content, onDelete, onReport }: MessageActionsProps) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
  const { user } = useAuth();
  const isSuperuser = !!user?.is_superuser;

  const handleCopy = useCallback((e: MouseEvent) => {
    e.preventDefault(); e.stopPropagation();
    try {
      navigator.clipboard?.writeText(content).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1400); })
        .catch(() => { const ta = document.createElement("textarea"); ta.value = content; ta.style.position = "fixed"; ta.style.opacity = "0"; document.body.appendChild(ta); ta.select(); try { document.execCommand("copy"); setCopied(true); setTimeout(() => setCopied(false), 1400); } catch {} document.body.removeChild(ta); });
    } catch {}
  }, [content]);

  const handleDelete = useCallback((e: MouseEvent) => { e.preventDefault(); e.stopPropagation(); onDelete?.(); }, [onDelete]);
  const handleReportClick = useCallback((e: MouseEvent) => { e.preventDefault(); e.stopPropagation(); setReportOpen(true); }, []);

  return (
    <>
      <div className={`message-actions ${styles.wrap}`}>
        <div className={`d-flex gap-1 ${styles.bar}`}>
          <button type="button" className={`message-action-btn ${styles.actionBtn}`} onMouseDown={handleCopy} title={t("chat.message.copy")}>
            <LucideIcon name="copy" size={14} />
            {copied && <span className="copy-toast">{t("chat.message.copied")}</span>}
          </button>
          {!isUser && (
            <button type="button" className={`message-action-btn ${styles.reportBtn}`} onMouseDown={handleReportClick} title={t("chat.message.report")}>
              <LucideIcon name="flag" size={14} />
            </button>
          )}
          {isSuperuser && onDelete != null && (
            <button type="button" className={`message-action-btn ${styles.deleteBtn}`} onMouseDown={handleDelete} title={t("chat.message.delete_admin")}>
              <LucideIcon name="trash-2" size={14} />
            </button>
          )}
        </div>
      </div>
      {reportOpen && <ReportReasonPicker onClose={() => setReportOpen(false)} onSubmit={(reason, detail) => { setReportOpen(false); onReport?.(reason, detail); }} />}
    </>
  );
}
