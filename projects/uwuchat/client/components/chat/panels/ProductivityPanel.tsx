import { useState } from "react";
import { JournalPanel } from "./JournalPanel";
import { CalendarPanel } from "./CalendarPanel";
import { TaskGoalPanel } from "./TaskGoalPanel";
import styles from "./ProductivityPanel.module.css";

type ProductivityTab = "journal" | "calendar" | "tasks";
const TABS: { id: ProductivityTab; label: string }[] = [
  { id: "journal", label: "Journal" }, { id: "calendar", label: "Calendar" }, { id: "tasks", label: "Tasks" },
];

export function ProductivityPanel({ chatbotId }: { chatbotId?: number | null }) {
  const [tab, setTab] = useState<ProductivityTab>("tasks");
  return (
    <div className={styles.panel}>
      <div className={styles.tabBar}>
        {TABS.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={tab === t.id ? styles.tabActive : styles.tabInactive}>{t.label}</button>
        ))}
      </div>
      <div className={styles.body}>
        {tab === "journal" && <JournalPanel />}
        {tab === "calendar" && <CalendarPanel chatbotId={chatbotId} />}
        {tab === "tasks" && <TaskGoalPanel />}
      </div>
    </div>
  );
}
