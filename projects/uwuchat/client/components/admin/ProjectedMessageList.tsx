import styles from "./ProjectedMessageList.module.css";

interface Message { role: string; content: string; }
interface Props { messages: Message[]; }

export default function ProjectedMessageList({ messages }: Props) {
  if (!messages.length) return <div className={styles.empty}>No visible messages at this point.</div>;
  return (
    <div className={styles.list}>
      {messages.map((m, i) => (
        <div key={i} className={styles.row}>
          <span className={styles.role}>{m.role === "user" ? "USER" : "BOT"}</span>
          <span className={styles.content}>{m.content.length > 200 ? m.content.slice(0, 200) + "…" : m.content}</span>
        </div>
      ))}
    </div>
  );
}
