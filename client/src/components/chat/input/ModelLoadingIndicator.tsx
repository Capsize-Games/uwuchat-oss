import LucideIcon from "../../shared/LucideIcon";
import styles from "./ModelLoadingIndicator.module.css";

export default function ModelLoadingIndicator({ visible }: { visible: boolean }) {
  if (!visible) return null;
  return (
    <div className={`p-2 rounded w-100 mt-2 ${styles.banner}`}>
      <div className="d-flex align-items-center gap-2">
        <LucideIcon name="loader" size={16} />
        <small className="text-theme-secondary">
          Loading model…
        </small>
      </div>
    </div>
  );
}
