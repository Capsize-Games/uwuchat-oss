import { Eye, EyeOff } from "lucide-react";
import { useCanvasContext } from "../CanvasContext";
import type { CanvasLayer } from "../useCanvasState";
import LayerThumbnail from "../LayerThumbnail";
import styles from "./LayerRow.module.css";

const ROW_H = 42;

export interface DragState {
  draggingId: string | null;
  dragOverId: string | null;
  dragPosition: "above" | "below";
  onDragStart: (id: string, e: React.DragEvent) => void;
  onDragOver: (id: string, e: React.DragEvent) => void;
  onDragLeave: () => void;
  onDrop: () => void;
  onDragEnd: () => void;
}

export interface EditState {
  editingId: string | null;
  editName: string;
  onNameChange: (v: string) => void;
  onCommit: (id: string) => void;
  onKeyDown: (e: React.KeyboardEvent, id: string) => void;
  onStart: (layer: CanvasLayer) => void;
}

interface Props {
  layer: CanvasLayer;
  depth: number;
  isActive: boolean;
  isSelected: boolean;
  displayName: string;
  drag: DragState;
  edit: EditState;
  onContextMenu: (x: number, y: number, id: string) => void;
}

export default function LayerRow({
  layer, depth, isActive, isSelected, displayName, drag, edit, onContextMenu,
}: Props) {
  const canvas = useCanvasContext();
  const hasMask = Array.isArray(layer.maskStrokes);
  const maskTarget = layer.maskTarget ?? "content";
  const indent = depth * 12;
  const isDragOver = drag.dragOverId === layer.id;
  const dropAbove = isDragOver && drag.dragPosition === "above";
  const dropBelow = isDragOver && drag.dragPosition === "below";

  const rowBgClass = isActive
    ? styles.rowActive
    : isSelected
      ? styles.rowSelected
      : isDragOver
        ? styles.rowDragOver
        : styles.rowDefault;

  const isHoverable = !isActive && !isSelected && drag.dragOverId !== layer.id;

  return (
    <div>
      {dropAbove && <div className={styles.dropIndicator} />}
      <div
        draggable
        onClick={(e) => {
          if (e.shiftKey) canvas.selectLayerRange(layer.id);
          else if (e.ctrlKey || e.metaKey) canvas.toggleLayerSelection(layer.id);
          else canvas.setActiveLayer(layer.id);
        }}
        onDragStart={(e) => drag.onDragStart(layer.id, e)}
        onDragOver={(e) => drag.onDragOver(layer.id, e)}
        onDragLeave={drag.onDragLeave}
        onDrop={(e) => { e.preventDefault(); drag.onDrop(); }}
        onDragEnd={drag.onDragEnd}
        onContextMenu={(e) => { e.preventDefault(); onContextMenu(e.clientX, e.clientY, layer.id); }}
        role="button"
        className={`${styles.row} ${rowBgClass} ${isHoverable ? styles.rowHoverable : ""}`}
        // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
        style={{
          padding: `0 6px 0 ${4 + indent}px`,
          height: ROW_H,
          cursor: drag.draggingId === layer.id ? "grabbing" : "default",
          borderLeft: `2px solid ${isSelected ? "#6399ff" : "transparent"}`,
        }}
      >
        <button
          title={layer.visible ? "Hide" : "Show"}
          onClick={(e) => { e.stopPropagation(); canvas.setLayerVisible(layer.id, !layer.visible); }}
          className={`${styles.eyeBtn} ${layer.visible ? styles.eyeBtnVisible : styles.eyeBtnHidden}`}
        >
          {layer.visible ? <Eye size={13} strokeWidth={1.75} /> : <EyeOff size={13} strokeWidth={1.75} />}
        </button>

        <LayerThumbnail
          layer={layer}
          docWidth={canvas.documentWidth}
          docHeight={canvas.documentHeight}
          type="content"
          active={isActive && maskTarget === "content"}
          size={30}
          onClick={(e) => {
            e.stopPropagation();
            canvas.setActiveLayer(layer.id);
            if (hasMask) canvas.setLayerMaskTarget(layer.id, "content");
          }}
        />

        {hasMask && (
          <LayerThumbnail
            layer={layer}
            docWidth={canvas.documentWidth}
            docHeight={canvas.documentHeight}
            type="mask"
            active={isActive && maskTarget === "mask"}
            size={30}
            onClick={(e) => {
              e.stopPropagation();
              canvas.setActiveLayer(layer.id);
              canvas.setLayerMaskTarget(layer.id, "mask");
            }}
          />
        )}

        {edit.editingId === layer.id ? (
          <input
            autoFocus
            value={edit.editName}
            onChange={(e) => edit.onNameChange(e.target.value)}
            onBlur={() => edit.onCommit(layer.id)}
            onKeyDown={(e) => edit.onKeyDown(e, layer.id)}
            onClick={(e) => e.stopPropagation()}
            className={styles.editInput}
          />
        ) : (
          <span
            className={`${styles.nameText} ${
              layer.visible
                ? isActive
                  ? styles.nameTextVisibleActive
                  : styles.nameTextVisible
                : styles.nameTextHidden
            }`}
            onDoubleClick={(e) => { e.stopPropagation(); edit.onStart(layer); }}
          >
            {displayName}
          </span>
        )}

        <span className={`text-mono-stat flex-shrink-0 ${styles.opacity}`}>
          {Math.round(layer.opacity * 100)}%
        </span>
      </div>
      {dropBelow && <div className={styles.dropIndicator} />}
    </div>
  );
}
