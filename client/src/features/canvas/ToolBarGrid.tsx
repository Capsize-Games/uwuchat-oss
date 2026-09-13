import { Grid3x3, Magnet, Lock, Unlock } from "lucide-react";
import { IconBtn } from "./ToolBarTools";
import type { ActiveGridArea } from "./useCanvasState";
import styles from "./ToolBarGrid.module.css";

interface ToolBarGridProps {
  showGrid: boolean;
  snapToGrid: boolean;
  activeGridArea: ActiveGridArea;
  gridLocked: boolean;
  onToggleGrid: () => void;
  onToggleSnap: () => void;
  onSetGridArea: (area: ActiveGridArea) => void;
  onToggleGridLock: () => void;
}

/**
 * Grid visibility, snapping, and active-grid-area controls for the toolbar.
 */
export default function ToolBarGrid({
  showGrid,
  snapToGrid,
  activeGridArea,
  gridLocked,
  onToggleGrid,
  onToggleSnap,
  onSetGridArea,
  onToggleGridLock,
}: ToolBarGridProps) {
  return (
    <div className={styles.root}>
      <IconBtn
        title="Toggle grid" active={showGrid} onClick={onToggleGrid}
      >
        <Grid3x3 size={15} strokeWidth={1.75} />
      </IconBtn>
      <IconBtn
        title="Snap to grid" active={snapToGrid} onClick={onToggleSnap}
      >
        <Magnet size={15} strokeWidth={1.75} />
      </IconBtn>
      <span className={styles.gridLabel}>
        Grid
      </span>
      <div className={styles.inputGroup}>
        <span className={styles.dimLabel}>
          W
        </span>
        <input
          type="number"
          value={activeGridArea.width}
          onChange={(e) => {
            const w = Number(e.target.value);
            const h = gridLocked ? w : activeGridArea.height;
            onSetGridArea({ ...activeGridArea, width: w, height: h });
          }}
          onBlur={(e) => {
            const w = Math.max(8, Math.round(Number(e.target.value) / 8) * 8);
            const h = gridLocked ? w : activeGridArea.height;
            onSetGridArea({ ...activeGridArea, width: w, height: h });
          }}
          className={styles.gridInput}
          title="Grid area width"
        />
        <IconBtn
          title={
            gridLocked
              ? "Unlock aspect ratio"
              : "Lock aspect ratio"
          }
          active={gridLocked}
          onClick={onToggleGridLock}
        >
          {gridLocked
            ? <Lock size={13} strokeWidth={1.75} />
            : <Unlock size={13} strokeWidth={1.75} />}
        </IconBtn>
        <span className={styles.dimLabel}>
          H
        </span>
        <input
          type="number"
          value={activeGridArea.height}
          onChange={(e) => {
            const h = Number(e.target.value);
            const w = gridLocked ? h : activeGridArea.width;
            onSetGridArea({ ...activeGridArea, width: w, height: h });
          }}
          onBlur={(e) => {
            const h = Math.max(8, Math.round(Number(e.target.value) / 8) * 8);
            const w = gridLocked ? h : activeGridArea.width;
            onSetGridArea({ ...activeGridArea, width: w, height: h });
          }}
          className={styles.gridInput}
          title="Grid area height"
        />
      </div>
    </div>
  );
}
