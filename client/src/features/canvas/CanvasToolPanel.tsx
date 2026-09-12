import {
  Move, SquareDashed, Lasso, Wand, Crop,
  PaintBucket, Pointer, Type, Pipette, Search,
  Brush, Eraser, Grid3x3, Ruler, MessageSquareHeart, Palette,
  ImageOff,
} from "lucide-react";
import LucideIcon from "../../components/shared/LucideIcon";
import type { ActiveTool } from "./useCanvasState";
import styles from "./CanvasToolPanel.module.css";

const TOOLS: { id: string; label: string; Icon: React.ComponentType<{ size?: number; strokeWidth?: number }> }[] = [
  { id: "move",    label: "Move (V)",      Icon: Move },
  { id: "select",  label: "Select (S)",    Icon: SquareDashed },
  { id: "lasso",   label: "Free Select",   Icon: Lasso },
  { id: "wand",    label: "Fuzzy Select",  Icon: Wand },
  { id: "crop",    label: "Crop",          Icon: Crop },
  { id: "bucket",  label: "Bucket Fill",   Icon: PaintBucket },
  { id: "smudge",  label: "Smudge",        Icon: Pointer },
  { id: "text",    label: "Text",          Icon: Type },
  { id: "pipette", label: "Color Picker",  Icon: Pipette },
  { id: "zoom",    label: "Zoom",          Icon: Search },
  { id: "brush",   label: "Brush (B)",     Icon: Brush },
  { id: "eraser",  label: "Eraser (E)",    Icon: Eraser },
  { id: "grid",    label: "Grid",          Icon: Grid3x3 },
  { id: "ruler",   label: "Ruler",         Icon: Ruler },
  { id: "remove-bg", label: "Remove Background", Icon: ImageOff },
];

interface Props {
  activeTool: ActiveTool;
  onToolChange: (tool: ActiveTool) => void;
  showImagePrompt: boolean;
  onToggleImagePrompt: () => void;
  showCanvasTools: boolean;
  onToggleCanvasTools: () => void;
  onCollapse?: () => void;
}

export default function CanvasToolPanel({
  activeTool,
  onToolChange,
  showImagePrompt,
  onToggleImagePrompt,
  showCanvasTools,
  onToggleCanvasTools,
  onCollapse,
}: Props) {
  const toolBtn = (id: string, Icon: React.ComponentType<{ size?: number; strokeWidth?: number }>) => {
    const isActive = !showImagePrompt && activeTool === id;
    return (
      <button
        key={id}
        title={TOOLS.find((t) => t.id === id)?.label ?? id}
        onClick={() => onToolChange(id as ActiveTool)}
        className={`${styles.toolBtn} ${isActive ? styles.toolBtnActive : ""}`}
      >
        <Icon size={14} strokeWidth={1.75} />
      </button>
    );
  };

  const TABS: { id: string; active: boolean; icon: React.ComponentType<{ size?: number; strokeWidth?: number }>; title: string; onClick: () => void }[] = [
    { id: "image-prompt", active: showImagePrompt, icon: MessageSquareHeart, title: "Image Prompt", onClick: onToggleImagePrompt },
    { id: "canvas-tools", active: showCanvasTools, icon: Palette, title: "Canvas Tools", onClick: onToggleCanvasTools },
  ];

  return (
    <div className={styles.root}>
      {/* ── Tab bar with collapse chevron ─────────────────────────────
       * Collapse chevron on the left, then palette toggle tabs styled
       * to match the right panel tab appearance. */}
      <div className={`d-flex flex-shrink-0 ${styles.tabBar}`}>
        <button
          type="button"
          title="Collapse panel"
          onClick={onCollapse}
          className={styles.collapseBtn}
        >
          <LucideIcon name="chevron-left" size={12} />
        </button>
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            title={t.title}
            onClick={t.onClick}
            className={`${styles.tabBtn} ${t.active ? styles.tabBtnActive : styles.tabBtnInactive}`}
          >
            <t.icon size={16} strokeWidth={1.75} />
          </button>
        ))}
      </div>


      {/* ── Palette of tools ──────────────────────────────────────────
       * Shown only when the canvas-tools palette is active. Each button
       * selects a drawing/editing mode (move, brush, eraser, etc.). */}
      {showCanvasTools && (
        <div className={styles.toolGrid}>
          {TOOLS.map((t) => toolBtn(t.id, t.Icon))}
        </div>
      )}

    </div>
  );
}
