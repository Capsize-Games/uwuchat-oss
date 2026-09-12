import type { ButtonHTMLAttributes } from "react";
import styles from "./WizardButton.module.css";

const SIZE_CLASSES: Record<string, Record<string, string>> = {
  primary: { sm: styles.primarySm, lg: styles.primaryLg, xl: styles.primaryXl },
  secondary: { sm: styles.secondarySm, lg: styles.secondaryLg, xl: styles.secondaryXl },
};

interface WizardButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary";
  size?: "sm" | "lg" | "xl";
}

export function WizardButton({
  variant = "secondary", size, style, className, disabled, ...rest
}: WizardButtonProps) {
  const baseCls = variant === "primary" ? styles.primary : styles.secondary;
  const sizeCls = size ? SIZE_CLASSES[variant]?.[size] ?? "" : "";
  const cls = [baseCls, sizeCls, className].filter(Boolean).join(" ");
  return (
    <button {...rest} disabled={disabled} className={cls} style={style} />
  );
}
