import LucideIcon from "../../shared/LucideIcon";
import styles from "./MessageAvatar.module.css";

export default function MessageAvatar({
  isUser,
  label,
}: {
  isUser: boolean;
  label: string;
}) {
  return (
    <div className="d-flex align-items-center gap-2 mb-1">
      <div className={styles.avatarCircle}>
        <LucideIcon name={isUser ? "user" : "bot-message-square"} size={16} />
      </div>
      <small className="fw-bold text-theme-secondary">
        {label}
      </small>
    </div>
  );
}
