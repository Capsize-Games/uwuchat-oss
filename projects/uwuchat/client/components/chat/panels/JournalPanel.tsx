import { useJournal } from "../../../hooks/useJournal";
import type { JournalEntry } from "../../../api/journal";
import styles from "./JournalPanel.module.css";

function formatDate(dateStr: string): string {
  try { const d = new Date(dateStr + "T12:00:00"); return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric", year: "numeric" }); }
  catch { return dateStr; }
}

function JournalRow({ entry }: { entry: JournalEntry }) {
  return (
    <div className={styles.entry}>
      <div className={styles.entryDate}>{formatDate(entry.entry_date)}</div>
      <div className={styles.entryBody}>{entry.body}</div>
    </div>
  );
}

export function JournalPanel() {
  const { entries, loading, error } = useJournal();
  if (loading) return <div className={styles.stateMsg}>Loading journal...</div>;
  if (error) return <div className={styles.errorMsg}>{error}</div>;
  if (entries.length === 0) return <div className={styles.stateMsg}>No journal entries yet. Chat with your UwU and they'll offer to write one!</div>;
  return <div className={styles.panel}>{entries.map((entry) => <JournalRow key={entry.id} entry={entry} />)}</div>;
}
