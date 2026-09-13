import { useEffect, useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { listAdminEvents, type ConversationEvent } from "../../api/admin";
import { useAuth } from "../../hooks/useAuth";
import styles from "./AdminReportsPanel.module.css";

export default function AdminReportsPanel() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const isSuperuser = !!user?.is_superuser;

  const [events, setEvents] = useState<ConversationEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // For now, we fetch across all chatbots. In the future, this can
  // be scoped to a specific chatbot via a prop/selector.
  const fetchReports = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // We need a chatbot_id for the API. Since reports span all
      // chatbots, we fetch from the system bot (id=1) which every
      // tenant has, and the events table is global.
      const result = await listAdminEvents(1, {
        event_types: "user_reported,content_risk_flagged",
        limit: 100,
      });
      setEvents(result.events);
      setTotal(result.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isSuperuser) {
      fetchReports();
    }
  }, [isSuperuser, fetchReports]);

  if (!isSuperuser) {
    return null;
  }

  if (loading) {
    return <div className={styles.loadingText}>{t("chat.report.loading")}</div>;
  }

  if (error) {
    return (
      <div className={`${styles.loadingText} ${styles.errorText}`}>
        {error}
      </div>
    );
  }

  return (
    <div className={styles.wrapper}>
      <div className={styles.headerRow}>
        <h6 className={styles.heading}>{t("chat.report.admin_title")}</h6>
        <button type="button" onClick={fetchReports} className={styles.refreshBtn}>
          {t("chat.report.refresh")}
        </button>
      </div>

      {events.length === 0 ? (
        <div className={styles.emptyText}>{t("chat.report.no_reports")}</div>
      ) : (
        <div className={styles.tableWrap}>
          <div className={styles.totalCount}>{total} {t("chat.report.total")}</div>
          <table className={styles.table}>
            <thead>
              <tr className={styles.tableHeader}>
                <th>{t("chat.report.col_time")}</th>
                <th>{t("chat.report.col_reporter")}</th>
                <th>{t("chat.report.col_type")}</th>
                <th>{t("chat.report.col_reason")}</th>
              </tr>
            </thead>
            <tbody>
              {events.map((ev) => (
                <tr key={ev.event_id} className={styles.tableRow}>
                  <td className={styles.tdTime}>
                    {ev.created_at ? new Date(ev.created_at).toLocaleString() : "—"}
                  </td>
                  {/* eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation */}
                  <td className={styles.tdName} style={{ color: ev.event_type === "content_risk_flagged" ? "rgba(255,200,100,0.8)" : "var(--theme-text-primary)" }}>
                    {ev.event_type === "content_risk_flagged" ? "system" : ev.actor}
                  </td>
                  <td className={styles.tdChip}>
                    <span className={ev.event_type === "content_risk_flagged" ? styles.chipAuto : styles.chipUser}>
                      {ev.event_type === "content_risk_flagged" ? t("chat.report.type_auto") : t("chat.report.type_user")}
                    </span>
                  </td>
                  <td className={styles.tdReason}>{_formatReason(ev)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function _formatReason(ev: ConversationEvent): string {
  if (ev.event_type === "content_risk_flagged") {
    const cats = (
      ev.payload?.categories as string[] | undefined
    );
    const score = ev.payload?.risk_score;
    const parts: string[] = [];
    if (cats?.length) {
      parts.push(cats.join(", "));
    }
    if (score !== undefined) {
      parts.push(`score=${Number(score).toFixed(2)}`);
    }
    return parts.join(" · ") || "high risk";
  }
  const reason = ev.payload?.reason;
  if (typeof reason === "string") {
    return reason;
  }
  return "—";
}
