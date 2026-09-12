import type { ReactNode, MouseEvent } from "react";
import LucideIcon from "../../shared/LucideIcon";
import styles from "./InfoItem.module.css";

export default function InfoItem({
  label,
  value,
  icon,
  editing,
  dimmed,
  onClick,
  onMouseDown,
  children,
  editor,
}: {
  label: string;
  value?: string;
  icon?: string;
  editing?: boolean;
  dimmed?: boolean;
  onClick?: (e: MouseEvent) => void;
  onMouseDown?: (e: MouseEvent) => void;
  children?: ReactNode;
  editor?: ReactNode;
}) {
  return (
    <div
      onClick={onClick}
      onMouseDown={onMouseDown}
      className={onClick ? styles.rowClickable : styles.row}
    >
      {icon && <LucideIcon name={icon} size={10} />}
      <span className={styles.rowLabel}>{label}</span>
      {editing && editor ? (
        <div
          className={styles.editorWrap}
          onClick={(e) => e.stopPropagation()}
        >
          {editor}
        </div>
      ) : value !== undefined ? (
        <span className={dimmed ? styles.rowValueDimmed : styles.rowValue}>
          {value}
        </span>
      ) : null}
      {children}
    </div>
  );
}
