import LucideIcon from "../../shared/LucideIcon";
import styles from "./EmptyPlaceholder.module.css";

export default function EmptyPlaceholder() {
  return (
    <div className={`d-flex align-items-center justify-content-center ${styles.root}`}>
      <div className={`d-flex flex-column align-items-center ${styles.card}`}>
        <div className={`d-flex align-items-center justify-content-center ${styles.iconCircle}`}>
          <LucideIcon name="bot-message-square" size={24} />
        </div>
        <p className={styles.text}>
          Start a conversation by typing a message below.
        </p>
      </div>
    </div>
  );
}
