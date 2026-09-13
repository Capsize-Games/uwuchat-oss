import LucideIcon from "../../shared/LucideIcon";
import styles from "./ActiveToolsDisplay.module.css";

export default function ActiveToolsDisplay({
  activeTools,
}: {
  activeTools: Array<{ tool_id: string; tool_name: string; details?: string | null }>;
}) {
  if (activeTools.length === 0) return null;

  const message =
    activeTools[0]?.details ?? "Analyzing request...";

  return (
    <div className={`p-2 rounded w-100 ${styles.banner}`}>
      <div className="d-flex align-items-center gap-2">
        <LucideIcon name="loader" size={16} />
        <small className="text-theme-secondary">{message}</small>
      </div>
    </div>
  );
}
