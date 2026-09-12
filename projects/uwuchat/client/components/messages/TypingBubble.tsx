import styles from "./TypingBubble.module.css";

export function TypingBubble({ name, emoji }: { name: string; emoji?: string }) {
  return (
    <div className={styles.wrap}>
      <div className={styles.avatarCircle}>{emoji || "🤖"}</div>
      <div className={styles.bubble}>
        <span className={styles.nameLabel}>{name}</span>
        <div className={styles.dots}>
          <span className={styles.dot} />
          <span className={styles.dot} />
          <span className={styles.dot} />
        </div>
      </div>
    </div>
  );
}
