import { FilePlus, Settings } from "lucide-react";
import styles from "./ToolBar.module.css";

interface ToolBarProps {
  onOpenSettings: () => void;
  onNewDocument: () => void;
}

export default function ToolBar({ onOpenSettings, onNewDocument }: ToolBarProps) {
  return (
    <div
      className={`d-flex align-items-center justify-content-between flex-shrink-0 user-select-none position-relative border-b-subtle ${styles.root}`}
    >
      <button className={styles.btn} onClick={onNewDocument}>
        <FilePlus size={13} strokeWidth={1.75} />
        New Document
      </button>

      <button className={styles.btn} onClick={onOpenSettings}>
        <Settings size={13} strokeWidth={1.75} />
        Canvas Settings
      </button>
    </div>
  );
}
