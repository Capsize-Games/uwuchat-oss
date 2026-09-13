import LucideIcon from "../../shared/LucideIcon";
import styles from "./PanelIconBtn.module.css";

export default function PanelIconBtn({
  icon,
  title,
  active,
  onClick,
}: {
  icon: string;
  title: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className={`${styles.btn} ${active ? styles.btnActive : styles.btnInactive}`}
    >
      <LucideIcon name={icon} size={13} />
    </button>
  );
}
