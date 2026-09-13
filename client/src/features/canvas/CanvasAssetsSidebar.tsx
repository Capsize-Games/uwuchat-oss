import { useState, useCallback, useRef, useEffect } from "react";
import { Layers, Image, ChevronRight } from "lucide-react";
import CanvasLayersSidebar from "./CanvasLayersSidebar";
import ImageBrowserPanel from "../../components/panels/ImageBrowserPanel";
import CollapsedRail, { type AssetTab } from "./sidebar/CollapsedRail";
import styles from "./CanvasAssetsSidebar.module.css";

const LS_W            = "airunner_assets_sidebar_w";
const LS_TAB          = "airunner_assets_sidebar_tab";
const LS_COLLAPSED    = "airunner_assets_sidebar_collapsed";
const LS_PARENT_TAB   = "canvas_asset_tab";

const TABS: { id: AssetTab; icon: React.ComponentType<{ size?: number }>; label: string }[] = [
  { id: "layers", icon: Layers, label: "Layers" },
  { id: "images", icon: Image, label: "Images" },
];

function loadWidth(): number {
  try {
    const v = localStorage.getItem(LS_W);
    if (v !== null) return Number(v);
    const old = localStorage.getItem("airunner_layers_sidebar_w");
    return old !== null ? Number(old) : 220;
  } catch { return 220; }
}

export default function CanvasAssetsSidebar({
  visible = true,
  activeTab,
}: {
  visible?: boolean;
  activeTab?: AssetTab;
}) {
  if (!visible) return null;

  const [tab, setTab] = useState<AssetTab>(() => {
    try { return (localStorage.getItem(LS_TAB) as AssetTab) ?? "layers"; }
    catch { return "layers"; }
  });

  const handleTabChange = useCallback((newTab: AssetTab) => {
    setTab(newTab);
    try { localStorage.setItem(LS_PARENT_TAB, newTab); } catch { /* */ }
  }, []);

  useEffect(() => {
    if (activeTab) setTab(activeTab);
  }, [activeTab]);
  const [width, setWidth] = useState(loadWidth);
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem(LS_COLLAPSED) === "true"; }
    catch { return false; }
  });

  const dragging = useRef(false);
  const startX = useRef(0);
  const startW = useRef(0);

  useEffect(() => { try { localStorage.setItem(LS_W, String(width)); } catch { /* */ } }, [width]);
  useEffect(() => { try { localStorage.setItem(LS_TAB, tab); } catch { /* */ } }, [tab]);
  useEffect(() => { try { localStorage.setItem(LS_COLLAPSED, String(collapsed)); } catch { /* */ } }, [collapsed]);

  const handleResizeMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    dragging.current = true;
    startX.current = e.clientX;
    startW.current = width;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    const onMove = (ev: MouseEvent) => {
      if (!dragging.current) return;
      setWidth(Math.max(260, Math.min(500, startW.current - (ev.clientX - startX.current))));
    };
    const onUp = () => {
      dragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }, [width]);

  const expand = (toTab?: AssetTab) => {
    if (toTab) handleTabChange(toTab);
    setCollapsed(false);
  };

  if (collapsed) {
    return (
      <div className={`flex-shrink-0 d-flex overflow-hidden ${styles.collapsedWrapper}`}>
        {/* Resize handle (kept for visual consistency, non-interactive when collapsed) */}
        <div className={styles.resizeHandle} />
        <CollapsedRail activeTab={tab} onExpand={expand} />
      </div>
    );
  }

  return (
    // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
    <div className="flex-shrink-0 d-flex overflow-hidden" style={{ width }}>
      {/* Resize handle */}
      <div
        onMouseDown={handleResizeMouseDown}
        className="resize-handle"
      />

      <div className={`flex-grow-1 d-flex flex-column overflow-hidden ${styles.panel}`}>

        {/* Tab bar */}
        <div className={`d-flex flex-shrink-0 border-b-subtle ${styles.tabBar}`}>
          {TABS.map((t) => {
            const isActive = tab === t.id;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => handleTabChange(t.id)}
                className={`${styles.tabBtn} ${isActive ? styles.tabBtnActive : styles.tabBtnInactive}`}
              >
                <t.icon size={16} />
              </button>
            );
          })}
          {/* Collapse chevron */}
          <button
            type="button"
            title="Collapse panel"
            onClick={() => setCollapsed(true)}
            className={styles.collapseBtn}
          >
            <ChevronRight size={16} />
          </button>
        </div>

        <div className="flex-grow-1 overflow-hidden d-flex flex-column min-h-0">
          {tab === "layers" ? <CanvasLayersSidebar /> : <ImageBrowserPanel />}
        </div>
      </div>
    </div>
  );
}
