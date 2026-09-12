import { useState, useCallback, type ChangeEvent } from "react";
import { useTranslation } from "react-i18next";
import LucideIcon from "@/components/shared/LucideIcon";
import styles from "./ReportReasonPicker.module.css";

interface ReportReasonPickerProps {
  onClose: () => void;
  onSubmit: (reason: string, detail: string) => void;
}

const REASONS = [
  "Inappropriate",
  "Harmful/unsafe",
  "Off-character",
  "Other",
] as const;

export default function ReportReasonPicker({
  onClose,
  onSubmit,
}: ReportReasonPickerProps) {
  const { t } = useTranslation();
  const [reason, setReason] = useState("");
  const [detail, setDetail] = useState("");
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = useCallback(() => {
    if (!reason) return;
    setSubmitted(true);
    onSubmit(reason, detail);
  }, [reason, detail, onSubmit]);

  const handleOverlayClick = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === e.currentTarget) onClose();
    },
    [onClose],
  );

  if (submitted) {
    return (
      <div onClick={handleOverlayClick} className={styles.overlay}>
        <div className={styles.dialogSubmitted}>
          <LucideIcon name="check-circle" size={28} />
          <p className={styles.submittedText}>
            {t("chat.report.received")}
          </p>
          <button type="button" onClick={onClose} className={styles.closeConfirmBtn}>
            {t("chat.report.close")}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div onClick={handleOverlayClick} className={styles.overlay}>
      <div className={styles.dialog}>
        <div className={styles.header}>
          <h6 className={styles.title}>
            <LucideIcon name="flag" size={14} />{" "}
            {t("chat.report.title")}
          </h6>
          <button type="button" onClick={onClose} className={styles.closeBtn}>
            <LucideIcon name="x" size={16} />
          </button>
        </div>

        <div className={styles.reasonList}>
          {REASONS.map((r) => (
            <button
              key={r}
              type="button"
              onClick={() => setReason(r)}
              className={
                reason === r
                  ? styles.reasonBtnSelected
                  : styles.reasonBtnUnselected
              }
            >
              {t(`chat.report.reason_${r.toLowerCase().replace(/[/\s]/g, "_")}`)}
            </button>
          ))}
        </div>

        <textarea
          value={detail}
          onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setDetail(e.target.value)}
          placeholder={t("chat.report.detail_placeholder")}
          rows={2}
          maxLength={500}
          className={styles.textarea}
        />

        <div className={styles.btnRow}>
          <button type="button" onClick={onClose} className={styles.cancelBtn}>
            {t("chat.report.cancel")}
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!reason}
            className={
              reason ? styles.submitBtnActive : styles.submitBtnDisabled
            }
          >
            {t("chat.report.submit")}
          </button>
        </div>
      </div>
    </div>
  );
}
