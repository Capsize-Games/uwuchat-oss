import type { ButtonHTMLAttributes } from "react";
import styles from "./SettingsButton.module.css";

interface SettingsButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "danger";
}

export function SettingsButton({
  variant,
  style,
  className,
  ...rest
}: SettingsButtonProps) {
  const variantCls = variant === "primary"
    ? styles.primary
    : variant === "secondary"
      ? styles.secondary
      : variant === "danger"
        ? styles.danger
        : styles.default;
  const cls = [variantCls, className].filter(Boolean).join(" ");
  return <button {...rest} className={cls} style={style} />;
}
