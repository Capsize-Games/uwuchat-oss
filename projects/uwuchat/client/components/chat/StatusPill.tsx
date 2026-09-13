import LucideIcon from "@/components/shared/LucideIcon";
import styles from "./StatusPill.module.css";

interface Props {
  iconName: string;
  label: string;
  statusKey: string;
  compact?: boolean;
}

/**
 * Compact icon-badge + shimmering status pill, shared between the
 * standalone pre-text StreamingStatus and the inline indicator
 * rendered inside StreamingMessageBubble.
 *
 * Uses `statusKey` as the React `key` on the content wrapper so that
 * CSS fade-in animations replay whenever the status changes.
 */
export default function StatusPill({ iconName, label, statusKey, compact }: Props) {
  return (
    <div className={styles.statusContent} key={statusKey}>
      <div className={styles.iconBadge}>
        <span className={styles.spinnerRing} />
        <LucideIcon
          name={iconName}
          size={compact ? 14 : 16}
          className={styles.icon}
        />
      </div>
      <div className={styles.statusBubble}>
        <span className={styles.statusText}>{label}</span>
        <span className={styles.dots} aria-hidden="true">
          <span className={styles.dot} />
          <span className={styles.dot} />
          <span className={styles.dot} />
        </span>
      </div>
    </div>
  );
}
