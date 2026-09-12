import LucideIcon from "../../shared/LucideIcon";
import styles from "./ToolbarToggle.module.css";

export default function ToolbarToggle({
  active,
  title,
  onClick,
  icon,
}: {
  active: boolean;
  title: string;
  onClick?: () => void;
  icon: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className={`${styles.btn} ${active ? styles.btnActive : styles.btnDefault}`}
    >
      <LucideIcon name={icon} size={15} />
    </button>
  );
}
