import { useCanvasContext } from "../CanvasContext";
import styles from "./LayerContextMenu.module.css";

interface Props {
  contextMenu: { x: number; y: number; layerId: string } | null;
  onClose: () => void;
}

export default function LayerContextMenu({ contextMenu, onClose }: Props) {
  const canvas = useCanvasContext();

  if (!contextMenu) return null;

  const isGroup = canvas.layerGroups.some((g) => g.id === contextMenu.layerId);
  const menuLayer = canvas.layers.find((l) => l.id === contextMenu.layerId);
  const hasMask = Array.isArray(menuLayer?.maskStrokes);

  const items = isGroup
    ? [
        {
          label: "Rename Group",
          danger: false,
          disabled: false,
          onClick: () => {
            const g = canvas.layerGroups.find((g) => g.id === contextMenu.layerId);
            if (g) canvas.renameGroup(contextMenu.layerId, prompt("Group name:", g.name) ?? g.name);
            onClose();
          },
        },
        {
          label: "Delete Group",
          danger: true,
          disabled: false,
          onClick: () => { canvas.deleteGroup(contextMenu.layerId); onClose(); },
        },
      ]
    : [
        {
          label: "Delete Layer",
          danger: true,
          disabled: false,
          onClick: () => { canvas.deleteLayer(contextMenu.layerId); onClose(); },
        },
        {
          label: "Delete Mask",
          danger: false,
          disabled: !hasMask,
          onClick: () => { if (hasMask) canvas.removeLayerMask(contextMenu.layerId); onClose(); },
        },
      ];

  return (
    <div
      onMouseDown={(e) => e.stopPropagation()}
      className={styles.menu}
      // eslint-disable-next-line no-restricted-syntax -- portal position from measured DOM rect
      style={{ top: contextMenu.y, left: contextMenu.x }}
    >
      {items.map((item) => (
        <button
          key={item.label}
          disabled={item.disabled}
          onClick={item.onClick}
          className={`${styles.menuItem} ${
            item.disabled
              ? styles.menuItemDisabled
              : item.danger
                ? styles.menuItemDanger
                : styles.menuItemNormal
          } ${!item.disabled ? styles.menuItemEnabled : styles.menuItemDisabled}`}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
