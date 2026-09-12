import { BotMessageSquare } from "lucide-react";
import styles from "./UwuLogo.module.css";

interface UwuLogoProps { size?: number; className?: string; }

export function UwuLogo({ size = 32, className }: UwuLogoProps) {
  const iconSize = Math.round(size * 1.1);
  const gap = Math.round(size * 0.25);
  return (
    <div className={className ? `${styles.wrapper} ${className}` : styles.wrapper} style={{ gap, fontSize: size } as React.CSSProperties}>
      <BotMessageSquare size={iconSize} strokeWidth={1.8} className={styles.icon} />
      {/* eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation */}
      <span className={styles.wordmark} style={{ fontSize: size }}>
        UwU<span className={styles.chatSpan}>chat</span>
      </span>
    </div>
  );
}
