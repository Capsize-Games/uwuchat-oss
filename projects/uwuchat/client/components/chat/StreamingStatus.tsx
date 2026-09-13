import StatusPill from "./StatusPill";
import styles from "./StreamingStatus.module.css";

interface Props {
  statusKey: string;
  iconName: string;
  label: string;
}

/**
 * Standalone pre-text status indicator for the system bot.
 *
 * Renders only the `<StatusPill>` (icon badge + status text) — no
 * bot avatar/name. The status pill already has its own icon +
 * animated ring; pairing it with the bot's avatar circle right next
 * to it reads as two unrelated "circle > text" units stacked side
 * by side. Once real text starts streaming, the avatar/name shows
 * up exactly once via `StreamingMessageBubble`, so identity is
 * still established — just not duplicated here.
 *
 * Accepts pre-stabilized status props from the
 * `useStreamingStatusQueue` hook, avoiding the direct derivation
 * from raw activeTools that caused flicker.
 */
export default function StreamingStatus({
  statusKey,
  iconName,
  label,
}: Props) {
  return (
    <div className="message-bubble">
      <div className={`w-100 ${styles.wrap}`}>
        <StatusPill
          iconName={iconName}
          label={label}
          statusKey={statusKey}
        />
      </div>
    </div>
  );
}
