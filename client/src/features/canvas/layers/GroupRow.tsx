import { Eye, EyeOff, SquareMinus, SquarePlus } from "lucide-react";
import { useCanvasContext } from "../CanvasContext";
import type { LayerGroup } from "../useCanvasState";
import styles from "./GroupRow.module.css";

interface DragProps {
  dragOverId: string | null;
  dragPosition: "above" | "below";
  dragSourceId: React.MutableRefObject<string | null>;
  onDragStart: (id: string, e: React.DragEvent) => void;
  onDragOver: (id: string, e: React.DragEvent) => void;
  onDragLeave: () => void;
  onDragEnd: () => void;
  onClearDrag: () => void;
}

interface Props {
  group: LayerGroup;
  drag: DragProps;
  isSelected: boolean;
  onContextMenu: (x: number, y: number, id: string) => void;
}

export default function GroupRow({ group, drag, isSelected, onContextMenu }: Props) {
  const canvas = useCanvasContext();
  const isDragOver = drag.dragOverId === group.id;
  const dropAbove = isDragOver && drag.dragPosition === "above";
  const dropBelow = isDragOver && drag.dragPosition === "below";

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    drag.onClearDrag();
    const srcId = drag.dragSourceId.current;
    if (!srcId) return;
    let orderIdx = canvas.displayOrder.indexOf(group.id);
    if (drag.dragPosition === "above") orderIdx += 1;
    const isLayer = canvas.layers.some((l) => l.id === srcId);
    if (isLayer) {
      canvas.moveLayerToGroup(srcId, group.id, orderIdx);
    } else {
      canvas.reorderDisplayItem(srcId, orderIdx);
    }
    drag.dragSourceId.current = null;
  };

  const rowBgClass = isSelected
    ? styles.rowSelected
    : isDragOver
      ? styles.rowDragOver
      : styles.rowDefault;

  return (
    <div>
      {dropAbove && <div className={styles.dropIndicator} />}
      <div
        draggable
        onClick={(e) => {
          if (e.ctrlKey || e.metaKey) {
            canvas.toggleLayerSelection(group.id);
          } else {
            canvas.setActiveLayer(group.id);
          }
        }}
        onContextMenu={(e) => { e.preventDefault(); onContextMenu(e.clientX, e.clientY, group.id); }}
        onDragStart={(e) => drag.onDragStart(group.id, e)}
        onDragOver={(e) => drag.onDragOver(group.id, e)}
        onDragLeave={drag.onDragLeave}
        onDrop={handleDrop}
        onDragEnd={drag.onDragEnd}
        role="button"
        className={`${styles.row} ${rowBgClass} ${!isSelected && drag.dragOverId !== group.id ? styles.rowHoverable : ""}`}
        // eslint-disable-next-line no-restricted-syntax -- computed dimension from state/prop
        style={{ borderLeft: `2px solid ${isSelected ? "#6399ff" : "transparent"}` }}
      >
        <button
          title={group.visible ? "Hide group" : "Show group"}
          onClick={(e) => { e.stopPropagation(); canvas.setGroupVisible(group.id, !group.visible); }}
          className={`${styles.eyeBtn} ${group.visible ? styles.eyeBtnVisible : styles.eyeBtnHidden}`}
        >
          {group.visible ? <Eye size={13} strokeWidth={1.75} /> : <EyeOff size={13} strokeWidth={1.75} />}
        </button>

        <button
          title={group.expanded ? "Collapse group" : "Expand group"}
          onClick={(e) => { e.stopPropagation(); canvas.toggleGroupExpanded(group.id); }}
          className={styles.expandBtn}
        >
          <div className={styles.expandBtnIcon}>
            {group.expanded ? (
              <SquareMinus size={12} strokeWidth={1.75} />
            ) : (
              <SquarePlus size={12} strokeWidth={1.75} />
            )}
          </div>
        </button>

        <span className={`${styles.name} ${group.visible ? styles.nameVisible : styles.nameHidden}`}>
          {group.name}
        </span>
        <span className={`text-mono-stat flex-shrink-0 ${styles.opacity}`}>
          {Math.round(group.opacity * 100)}%
        </span>
      </div>
      {dropBelow && <div className={styles.dropIndicator} />}
    </div>
  );
}
