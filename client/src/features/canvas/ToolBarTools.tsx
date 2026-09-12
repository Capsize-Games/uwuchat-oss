import {
  SquareDashed, Brush, Eraser, Move, LassoSelect,
} from "lucide-react";
import type { ActiveTool } from "./useCanvasState";
import styles from "./ToolBarTools.module.css";

/**
 * Tool definitions consumed by the main ToolBar component.
 */
export const TOOLS: {
  id: ActiveTool;
  label: string;
  key: string;
  Icon: React.ComponentType<{
    size?: number; strokeWidth?: number;
  }>;
}[] = [
  { id: "select", label: "Select", key: "S", Icon: SquareDashed },
  { id: "lasso",  label: "Lasso",  key: "L", Icon: LassoSelect },
  { id: "brush",  label: "Brush",  key: "B", Icon: Brush },
  { id: "eraser", label: "Eraser", key: "E", Icon: Eraser },
  { id: "move",   label: "Move",   key: "V", Icon: Move },
];

interface IconBtnProps {
  title: string;
  active?: boolean;
  danger?: boolean;
  disabled?: boolean;
  onClick?: () => void;
  children: React.ReactNode;
}

/**
 * Icon button used in the toolbar (supports an active/highlighted state).
 *
 * Note: there is a separate, simpler IconBtn in IconBtn.tsx used by the
 * layers sidebar. Do not conflate the two.
 */
export function IconBtn({
  title,
  active,
  danger,
  disabled,
  onClick,
  children,
}: IconBtnProps) {
  const classNames = [
    styles.iconBtn,
    active ? styles.iconBtnActive : "",
    danger ? styles.iconBtnDanger : "",
    disabled ? styles.iconBtnDisabled : "",
  ].filter(Boolean).join(" ");

  return (
    <button
      title={title}
      disabled={disabled}
      onClick={onClick}
      className={classNames}
    >
      {children}
    </button>
  );
}

/**
 * Thin vertical divider rendered between toolbar sections.
 */
export function Divider() {
  return <div className={styles.divider} />;
}
