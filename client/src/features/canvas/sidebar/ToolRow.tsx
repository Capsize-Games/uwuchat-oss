import { SquareDashed, Brush, Eraser, Move, Undo2, Redo2 } from "lucide-react";
import { useCanvasContext } from "../CanvasContext";
import type { ActiveTool } from "../useCanvasState";
import styles from "./ToolRow.module.css";

const TOOLS: { id: ActiveTool; label: string; Icon: React.ComponentType<{ size?: number; strokeWidth?: number }> }[] = [
  { id: "move",   label: "Move (V)",   Icon: Move },
  { id: "select", label: "Select (S)", Icon: SquareDashed },
  { id: "brush",  label: "Brush (B)",  Icon: Brush },
  { id: "eraser", label: "Eraser (E)", Icon: Eraser },
];

export default function ToolRow() {
  const canvas = useCanvasContext();
  return (
    <div
      className={`d-flex align-items-center flex-shrink-0 border-b-subtle ${styles.root}`}
    >
      {TOOLS.map(({ id, label, Icon }) => (
        <button
          key={id}
          title={label}
          onClick={() => canvas.setActiveTool(id)}
          className={`${styles.toolBtn} ${canvas.activeTool === id ? styles.toolBtnActive : ""}`}
        >
          <Icon size={14} strokeWidth={1.75} />
        </button>
      ))}
      <div className="sep-v" />
      <button title="Undo (Ctrl+Z)" className={styles.iconBtn} onClick={canvas.undo}>
        <Undo2 size={13} strokeWidth={1.75} />
      </button>
      <button title="Redo (Ctrl+Shift+Z)" className={styles.iconBtn} onClick={canvas.redo}>
        <Redo2 size={13} strokeWidth={1.75} />
      </button>
    </div>
  );
}
