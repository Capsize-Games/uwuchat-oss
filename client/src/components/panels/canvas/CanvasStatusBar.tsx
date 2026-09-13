import { ZoomIn, ZoomOut, Crosshair, Expand } from "lucide-react";
import type { CanvasLayer } from "../../../features/canvas/useCanvasState";
import styles from "./CanvasStatusBar.module.css";

export interface CanvasStatusBarProps {
  documentWidth: number;
  documentHeight: number;
  zoom: number;
  gridWidth: number;
  gridHeight: number;
  activeLayer: CanvasLayer | null;
  isFitToView: boolean;
  isCenterView: boolean;
  onZoomOut: () => void;
  onZoomReset: () => void;
  onZoomIn: () => void;
  onCenterView: () => void;
  onFitView: () => void;
}

export default function CanvasStatusBar({
  documentWidth,
  documentHeight,
  zoom,
  gridWidth,
  gridHeight,
  activeLayer,
  isFitToView,
  isCenterView,
  onZoomOut,
  onZoomReset,
  onZoomIn,
  onCenterView,
  onFitView,
}: CanvasStatusBarProps) {
  const zoomPct = `${Math.round(zoom * 100)}%`;

  return (
    <div className={styles.bar}>
      <span>{documentWidth} &times; {documentHeight}</span>
      {activeLayer && <span>Layer: {activeLayer.name}</span>}

      <div className="flex-grow-1" />

      {/* Zoom controls */}
      <div className={`d-flex align-items-center ${styles.zoomGroup}`}>
        <button className={styles.iconBtn} title="Zoom out" onClick={onZoomOut}>
          <ZoomOut size={13} strokeWidth={1.75} />
        </button>
        <button
          className={styles.zoomReset}
          title="Reset zoom to 100%"
          onClick={onZoomReset}
        >
          {zoomPct}
        </button>
        <button className={styles.iconBtn} title="Zoom in" onClick={onZoomIn}>
          <ZoomIn size={13} strokeWidth={1.75} />
        </button>
        <button
          className={isCenterView ? styles.iconBtnActive : styles.iconBtn}
          title={isCenterView ? "Center view (active)" : "Center view"}
          onClick={onCenterView}
        >
          <Crosshair size={13} strokeWidth={1.75} />
        </button>
        <button
          className={isFitToView ? styles.iconBtnActive : styles.iconBtn}
          title={isFitToView ? "Fit to view (active)" : "Fit to view"}
          onClick={onFitView}
        >
          <Expand size={13} strokeWidth={1.75} />
        </button>
      </div>
    </div>
  );
}
