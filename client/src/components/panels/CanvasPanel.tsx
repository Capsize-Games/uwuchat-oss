import {
  useRef,
  useState,
  useCallback,
  useEffect,
} from "react";
import { removeBackground } from "../../api/art";
import { renderSingleLayer } from "../../features/canvas/compositeCanvas";
import Konva from "konva";
import { RefreshCcw, RefreshCcwDot } from "lucide-react";
import LucideIcon from "../shared/LucideIcon";
import {
  useCanvasContext,
  useCanvasDocument,
  useCanvasSync,
} from "../../features/canvas";
import { useGhostStrokes } from "../../features/canvas/useGhostStrokes";
import type { CanvasStageHandle } from "../../features/canvas/CanvasStage";
import CanvasStage from "../../features/canvas/CanvasStage";
import styles from "./CanvasPanel.module.css";
import CanvasSettingsModal from "../../features/canvas/CanvasSettingsModal";
import ImageDropModal, {
  type DropResizeMode,
  fitDimensions,
} from "../../features/canvas/ImageDropModal";
import CanvasAssetsSidebar from "../../features/canvas/CanvasAssetsSidebar";
import CanvasStatusBar from "./canvas/CanvasStatusBar";
import ArtPromptPanel from "./ArtPromptPanel";
import CanvasToolPanel from "../../features/canvas/CanvasToolPanel";
import BrushControls from "../../features/canvas/sidebar/BrushControls";
import MoveControls from "../../features/canvas/sidebar/MoveControls";
import LassoControls from "../../features/canvas/sidebar/LassoControls";
import WandControls from "../../features/canvas/sidebar/WandControls";
import CropControls from "../../features/canvas/sidebar/CropControls";
import BucketControls from "../../features/canvas/sidebar/BucketControls";
import SmudgeControls from "../../features/canvas/sidebar/SmudgeControls";
import PipetteControls from "../../features/canvas/sidebar/PipetteControls";
import ZoomControls from "../../features/canvas/sidebar/ZoomControls";
import TextControls from "../../features/canvas/sidebar/TextControls";
import GridControls from "../../features/canvas/sidebar/GridControls";
import RulerControls from "../../features/canvas/sidebar/RulerControls";
import { useCanvasImageDrop } from "./canvas/useCanvasImageDrop";
import { useMenuAction } from "../layout/action-menu-bar";
import { useCanvasPrefs } from "../../hooks/useCanvasPrefs";

const LEFT_PANEL_MIN = 220;
const LEFT_PANEL_MAX = 560;

const TOOL_LABELS: Record<string, string> = {
  move:    "Move",
  select:  "Selection",
  lasso:   "Free Select",
  wand:    "Fuzzy Select",
  crop:    "Crop",
  bucket:  "Bucket Fill",
  smudge:  "Smudge",
  text:    "Text",
  pipette: "Color Picker",
  zoom:    "Zoom",
  brush:   "Brush",
  eraser:  "Eraser",
  grid:    "Grid",
  ruler:   "Ruler",
};

let leftPanelDrag: { startX: number; startW: number; setW: (w: number) => void } | null = null;
if (typeof window !== "undefined") {
  window.addEventListener("mousemove", (e: MouseEvent) => {
    if (!leftPanelDrag) return;
    const delta = e.clientX - leftPanelDrag.startX;
    leftPanelDrag.setW(Math.max(LEFT_PANEL_MIN, Math.min(LEFT_PANEL_MAX, leftPanelDrag.startW + delta)));
  });
  window.addEventListener("mouseup", () => {
    if (!leftPanelDrag) return;
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
    leftPanelDrag = null;
  });
}

export default function CanvasPanel() {
  const canvas = useCanvasContext();

  const stageRef = useRef<Konva.Stage>(null!) as React.RefObject<Konva.Stage>;
  const gridLayerRef = useRef<Konva.Layer>(null!) as React.RefObject<Konva.Layer>;
  const maskLayerRef = useRef<Konva.Layer>(null!) as React.RefObject<Konva.Layer>;
  const canvasHandleRef = useRef<CanvasStageHandle>(null);

  const ghostStrokes = useGhostStrokes();

  const {
    fitToView: isFitToView, setFitToView: setIsFitToView,
    centerView: isCenterView, setCenterView: setIsCenterView,
    assetTab,
    genType: generationType, setGenType: setGenerationType,
    showImagePrompt, setShowImagePrompt,
    showCanvasTools, setShowCanvasTools,
    leftPanelW, setLeftPanelW,
    leftPanelCollapsed, setLeftPanelCollapsed,
  } = useCanvasPrefs();

  const [zoom, setZoom] = useState(1);
  const [showSettings, setShowSettings] = useState(false);
  const [isRemovingBg, setIsRemovingBg] = useState(false);
  const [showNewDocModal, setShowNewDocModal] = useState(false);

  const canvasSync = useCanvasSync({
    onDocument: (json) => {
      if (json) {
        ghostStrokes.clearAll();
        canvas.loadFromJSON(json);
      }
    },
    onLiveStroke: ghostStrokes.applyLiveDelta,
    onStrokeEnd: (msg) => ghostStrokes.clearGhost(msg.sessionId),
  });

  const documentString = JSON.stringify(canvas.getPersistableState());
  const [lastSavedDigest, setLastSavedDigest] = useState<string | null>(null);
  const currentDigest = documentString;
  const isDirty = currentDigest !== lastSavedDigest;

  const { isLoaded } = useCanvasDocument({
    documentString,
    onLoad: canvas.loadFromJSON,
    wsSend: canvasSync.send,
    isDirty,
    onSaved: () => setLastSavedDigest(currentDigest),
  });

  const {
    pendingDrop,
    showDropModal,
    setShowDropModal,
    handleDragOver,
    handleDrop,
    queueDrop,
    viewportCenter,
    useCanvasPlaceImage,
  } = useCanvasImageDrop(stageRef);

  useCanvasPlaceImage(queueDrop, viewportCenter);

  const handleDropConfirm = useCallback(
    (mode: DropResizeMode) => {
      if (!pendingDrop) return;
      const { base64, x, y, naturalW, naturalH } = pendingDrop;
      let w = naturalW;
      let h = naturalH;
      if (mode === "fit-canvas") {
        const fit = fitDimensions(naturalW, naturalH, canvas.documentWidth, canvas.documentHeight);
        w = fit.w;
        h = fit.h;
      }
      canvas.placeImageOnNewLayer(base64, Math.max(0, x - w / 2), Math.max(0, y - h / 2), w, h);
    },
    [pendingDrop, canvas],
  );

  const handleNewDocument = useCallback(
    () => setShowNewDocModal(true),
    [],
  );

  // ── Export the visible canvas as a PNG file ────────────────────────
  const handleExport = useCallback(async () => {
    const w = canvas.documentWidth;
    const h = canvas.documentHeight;
    if (w <= 0 || h <= 0) return;

    // Reuse the existing off-screen compositor so every visible layer,
    // stroke, text node and opacity is faithfully flattened.
    const { renderVisibleComposite } = await import(
      "../../features/canvas/compositeCanvas"
    );
    const out = await renderVisibleComposite({
      layers: canvas.layers,
      layerGroups: canvas.layerGroups,
      displayOrder: canvas.displayOrder,
      documentWidth: w,
      documentHeight: h,
    });
    if (!out) return;

    // Convert to PNG blob
    const blob: Blob = await new Promise((resolve, reject) => {
      out.toBlob((b) => {
        if (b) resolve(b);
        else reject(new Error("Failed to create PNG blob"));
      }, "image/png");
    });

    const fileName = `canvas-export-${Date.now()}.png`;

    // Prefer the File System Access API (Chromium) for a native save
    // dialog; fall back to <a download> for all other browsers.
    if ("showSaveFilePicker" in window) {
      try {
        const handle = await (
          window as Window &
            typeof globalThis
        ).showSaveFilePicker({
          suggestedName: fileName,
          types: [
            {
              description: "PNG Image",
              accept: { "image/png": [".png"] },
            },
          ],
        });
        const writable = await handle.createWritable();
        await writable.write(blob);
        await writable.close();
        return;
      } catch (err: unknown) {
        // User cancelled – silently abort
        if (
          err instanceof DOMException &&
          err.name === "AbortError"
        ) {
          return;
        }
        // API unavailable or other error – fall through to fallback
      }
    }

    // Fallback: trigger an immediate download for non-Chromium browsers
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = fileName;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [canvas.documentWidth, canvas.documentHeight, canvas.layers, canvas.layerGroups, canvas.displayOrder]);

  // ── Respond to action-menu events ──────────────────────────────────
  useMenuAction(
    useCallback(
      (action) => {
        switch (action.type) {
          case "file:new-document":
            handleNewDocument();
            break;
          case "file:export":
            handleExport();
            break;
          case "edit:undo":
            canvas.undo();
            break;
          case "edit:redo":
            canvas.redo();
            break;
          case "edit:preferences":
            setShowSettings(true);
            break;
          case "view:toggle-ruler":
            canvas.setRulerShowRuler(
              !canvas.rulerShowRuler,
            );
            break;
          case "view:toggle-grid":
            canvas.setGridShowGrid(
              !canvas.gridShowGrid,
            );
            break;
        }
      },
      [canvas, handleNewDocument, handleExport],
    ),
  );

  // Sync ruler/grid state back to the action menu bar whenever it
  // changes (e.g. user toggles from the sidebar).
  useEffect(() => {
    window.dispatchEvent(
      new CustomEvent("airunner:canvas-state", {
        detail: {
          rulerShowRuler: canvas.rulerShowRuler,
          gridShowGrid: canvas.gridShowGrid,
        },
      }),
    );
  }, [canvas.rulerShowRuler, canvas.gridShowGrid]);

  const handleNewDocumentConfirm = useCallback(
    (w: number, h: number, bg: string) => {
      canvas.resetDocument(bg);
      canvas.setDocumentSize(w, h);
      canvas.setDocumentBgColor(bg);
    },
    [canvas],
  );

  const handleApplySettings = useCallback(
    (w: number, h: number, bg: string) => {
      canvas.setDocumentSize(w, h);
      canvas.setDocumentBgColor(bg);
    },
    [canvas],
  );


  if (!isLoaded) {
    return (
      <div className="canvas-panel d-flex align-items-center justify-content-center h-100">
        <div className="spinner-border spinner-border-sm text-theme-secondary" role="status" />
      </div>
    );
  }

  const toolSettingsLabel = showImagePrompt
    ? "Image Prompt"
    : (TOOL_LABELS[canvas.activeTool] ?? canvas.activeTool);

  const showBrushControls = !showImagePrompt &&
    (canvas.activeTool === "brush" || canvas.activeTool === "eraser");
  const showMoveControls  = !showImagePrompt && canvas.activeTool === "move";
  const showLassoControls = !showImagePrompt && canvas.activeTool === "lasso";
  const showWandControls  = !showImagePrompt && canvas.activeTool === "wand";
  const showCropControls  = !showImagePrompt && canvas.activeTool === "crop";
  const showBucketControls = !showImagePrompt && canvas.activeTool === "bucket";
  const showSmudgeControls = !showImagePrompt && canvas.activeTool === "smudge";
  const showPipetteControls = !showImagePrompt && canvas.activeTool === "pipette";
  const showZoomControls = !showImagePrompt && canvas.activeTool === "zoom";
  const showTextControls = !showImagePrompt && canvas.activeTool === "text";
  const showGridControls = !showImagePrompt && canvas.activeTool === "grid";
  const showRulerControls = !showImagePrompt && canvas.activeTool === "ruler";
  const showRemoveBg = !showImagePrompt && canvas.activeTool === "remove-bg";

  return (
    <div
      className={`canvas-panel d-flex h-100 overflow-hidden flex-column ${styles.panelBg}`}
    >
      <div className="flex-grow-1 d-flex flex-column overflow-hidden min-w-0 min-h-0">
        <div className="flex-grow-1 d-flex flex-row overflow-hidden min-h-0">

          {/* ── Left panel (collapsible) ──────────────────────────────────── */}
          {leftPanelCollapsed ? (
            /* Collapsed rail — thin bar with expand chevron + tab icons */
            <div
              className={`flex-shrink-0 d-flex overflow-hidden ${styles.railOuter}`}
            >
              <div
                className={`flex-shrink-0 d-flex flex-column align-items-center overflow-hidden ${styles.railInner}`}
              >
                <button
                  title="Expand panel"
                  className={styles.railBtn}
                  onClick={() => setLeftPanelCollapsed(false)}
                >
                  <LucideIcon name="chevron-right" size={14} />
                </button>

                <div className={`sep-h ${styles.railSep}`} />

                {/* Tab indicator — Image Prompt */}
                <button
                  title="Image Prompt"
                  className={showImagePrompt ? styles.railBtnActive : styles.railBtn}
                  onClick={() => {
                    setShowImagePrompt(true);
                    setShowCanvasTools(false);
                    setLeftPanelCollapsed(false);
                  }}
                >
                  <LucideIcon name="message-square-heart" size={14} />
                </button>

                {/* Tab indicator — Canvas Tools */}
                <button
                  title="Canvas Tools"
                  className={showCanvasTools ? styles.railBtnActive : styles.railBtn}
                  onClick={() => {
                    setShowCanvasTools(true);
                    setShowImagePrompt(false);
                    setLeftPanelCollapsed(false);
                  }}
                >
                  <LucideIcon name="palette" size={14} />
                </button>
              </div>
            </div>
          ) : (
            /* Expanded panel */
            <div
              className={styles.leftPanel}
              // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
              style={{ width: leftPanelW }}
            >
              <div className={styles.leftPanelInner}>

                <CanvasToolPanel
                  activeTool={canvas.activeTool}
                  onToolChange={(tool) => {
                    canvas.setActiveTool(tool);
                    setShowImagePrompt(false);
                  }}
                  showImagePrompt={showImagePrompt}
                  onToggleImagePrompt={() => {
                    if (showImagePrompt) return; // can't untoggle
                    setShowImagePrompt(true);
                    setShowCanvasTools(false);
                  }}
                  showCanvasTools={showCanvasTools}
                  onToggleCanvasTools={() => {
                    if (showCanvasTools) return; // can't untoggle
                    setShowCanvasTools(true);
                    setShowImagePrompt(false);
                  }}
                  onCollapse={() => setLeftPanelCollapsed(true)}
                />

                {/* Tool settings section */}
                <div className={styles.toolSettingsWrapper}>
                  <div className={styles.toolSettingsBar}>
                    <span className={styles.toolSettingsLabel}>
                      {toolSettingsLabel}
                    </span>
                  </div>
                  <div className={styles.toolSettingsScroll}>
                    {showImagePrompt && <ArtPromptPanel visible={true} generationType={generationType} onGenerationTypeChange={setGenerationType} />}
                    {showBrushControls && <BrushControls />}
                    {showMoveControls && <MoveControls />}
                    {showLassoControls && <LassoControls />}
                    {showWandControls && <WandControls />}
                    {showCropControls && <CropControls />}
                    {showBucketControls && <BucketControls />}
                    {showSmudgeControls && <SmudgeControls />}
                    {showPipetteControls && <PipetteControls />}
                    {showZoomControls && <ZoomControls />}
                    {showTextControls && <TextControls />}
                    {showGridControls && <GridControls />}
                    {showRulerControls && <RulerControls />}
                    {showRemoveBg && (
                      <div className={styles.removeBgWrap}>
                        <button
                          type="button"
                          className={`btn btn-primary btn-sm ${styles.removeBgBtn}`}
                          disabled={isRemovingBg}
                          onClick={async () => {
                            setIsRemovingBg(true);
                            try {
                              const selectedLayers = canvas.layers.filter(
                                (l) => canvas.selectedLayerIds.includes(l.id),
                              );
                              if (selectedLayers.length === 0) return;
                              const updates: Array<{ layerId: string; base64: string; x: number; y: number; width: number; height: number }> = [];
                              for (const layer of selectedLayers) {
                                const layerCanvas = await renderSingleLayer(
                                  layer,
                                  canvas.documentWidth,
                                  canvas.documentHeight,
                                );
                                if (!layerCanvas) continue;
                                const rawB64 = layerCanvas.toDataURL("image/png").split(",")[1];
                                const resultB64 = await removeBackground(rawB64);
                                updates.push({
                                  layerId: layer.id,
                                  base64: `data:image/png;base64,${resultB64}`,
                                  x: 0, y: 0,
                                  width: canvas.documentWidth,
                                  height: canvas.documentHeight,
                                });
                              }
                              if (updates.length > 0) {
                                canvas.replaceLayersImages(updates);
                              }
                            } catch (err) {
                              console.error("Background removal failed:", err);
                            } finally {
                              setIsRemovingBg(false);
                            }
                          }}
                        >
                          {isRemovingBg && (
                            <span className={`spinner-border spinner-border-sm ${styles.removeBgSpinner}`} role="status" />
                          )}
                          Remove background
                        </button>
                      </div>
                    )}
                  </div>
                </div>

                {/* Bottom row: reset presets — only for canvas tools tab */}
                {showCanvasTools && (
                <div className={styles.bottomRow}>
                  <button
                    title="Reset tool presets"
                    className={styles.resetBtn}
                    onClick={() => canvas.resetToolPresets(canvas.activeTool)}
                  >
                    <RefreshCcw size={13} strokeWidth={1.75} />
                  </button>
                  <button
                    title="Reset all tool presets"
                    className={styles.resetBtn}
                    onClick={() => canvas.resetAllToolPresets()}
                  >
                    <RefreshCcwDot size={13} strokeWidth={1.75} />
                  </button>
                </div>
                )}

              </div>

              {/* Resize handle on right edge of left panel */}
              <div
                className="resize-handle"
                onMouseDown={(e) => {
                  e.preventDefault();
                  leftPanelDrag = { startX: e.clientX, startW: leftPanelW, setW: setLeftPanelW };
                  document.body.style.cursor = "col-resize";
                  document.body.style.userSelect = "none";
                }}
              />
            </div>
          )}

          {/* ── Canvas viewport ─────────────────────────────────────────── */}
          <div
            className={`flex-grow-1 overflow-hidden position-relative d-flex flex-column ${styles.viewportBg}`}
            onDragOver={handleDragOver}
            onDrop={handleDrop}
          >
            <div className="flex-grow-1 min-h-0 overflow-hidden">
              <CanvasStage
                ref={canvasHandleRef}
                documentWidth={canvas.documentWidth}
                documentHeight={canvas.documentHeight}
                documentBgColor={canvas.documentBgColor}
                layers={canvas.layers}
                layerGroups={canvas.layerGroups}
                displayOrder={canvas.displayOrder}
                activeLayerId={canvas.activeLayerId}
                activeGridArea={canvas.activeGridArea}
                activeTool={canvas.activeTool}
                moveMode={canvas.moveMode}
                selectedLayerIds={canvas.selectedLayerIds}
                brushSize={canvas.brushSize}
                brushColor={canvas.brushColor}
                maskStrokes={canvas.maskStrokes}
                inpaintMaskStrokes={canvas.inpaintMaskStrokes}
                generationType={generationType}
                showGrid={canvas.gridShowGrid}
                gridSize={canvas.gridSize}
                gridColor={canvas.gridColor}
                showRuler={canvas.rulerShowRuler}
                snapToGrid={canvas.snapToGrid}
                onAddStroke={canvas.addStroke}
                onMoveImage={canvas.moveImage}
                onMoveLayer={canvas.moveLayer}
                onAddMaskStroke={canvas.addMaskStroke}
                onAddLayerMaskStroke={canvas.addLayerMaskStroke}
                onAddInpaintMaskStroke={canvas.addInpaintMaskStroke}
                setActiveGridArea={canvas.setActiveGridArea}
                onUndo={canvas.undo}
                onRedo={canvas.redo}
                setActiveTool={canvas.setActiveTool}
                setActiveLayer={canvas.setActiveLayer}
                onZoomChange={setZoom}
                isFitToView={isFitToView}
                isCenterView={isCenterView}
                onFitToViewChange={setIsFitToView}
                onCenterViewChange={setIsCenterView}
                gridLayerRef={gridLayerRef}
                maskLayerRef={maskLayerRef}
                stageRef={stageRef}
                ghostLayerRef={ghostStrokes.ghostLayerRef}
                sendLiveStroke={canvasSync.sendLiveStroke}
                sendStrokeEnd={canvasSync.sendStrokeEnd}
              />
            </div>
            <CanvasStatusBar
              documentWidth={canvas.documentWidth}
              documentHeight={canvas.documentHeight}
              zoom={zoom}
              gridWidth={canvas.activeGridArea.width}
              gridHeight={canvas.activeGridArea.height}
              activeLayer={canvas.activeLayer}
              isFitToView={isFitToView}
              isCenterView={isCenterView}
              onZoomOut={() => canvasHandleRef.current?.zoomOut()}
              onZoomReset={() => canvasHandleRef.current?.zoomReset()}
              onZoomIn={() => canvasHandleRef.current?.zoomIn()}
              onCenterView={() => canvasHandleRef.current?.centerView()}
              onFitView={() => canvasHandleRef.current?.fitView()}
            />
          </div>

          <CanvasAssetsSidebar visible={assetTab !== null} activeTab={assetTab ?? "layers"} />
        </div>
      </div>

      <CanvasSettingsModal
        show={showSettings}
        documentWidth={canvas.documentWidth}
        documentHeight={canvas.documentHeight}
        documentBgColor={canvas.documentBgColor}
        onApply={handleApplySettings}
        onHide={() => setShowSettings(false)}
      />
      <CanvasSettingsModal
        show={showNewDocModal}
        newDocumentMode
        documentWidth={canvas.documentWidth}
        documentHeight={canvas.documentHeight}
        documentBgColor={canvas.documentBgColor}
        onApply={handleNewDocumentConfirm}
        onHide={() => setShowNewDocModal(false)}
      />
      <ImageDropModal
        show={showDropModal}
        naturalW={pendingDrop?.naturalW ?? 0}
        naturalH={pendingDrop?.naturalH ?? 0}
        gridW={canvas.activeGridArea.width}
        gridH={canvas.activeGridArea.height}
        canvasW={canvas.documentWidth}
        canvasH={canvas.documentHeight}
        onConfirm={handleDropConfirm}
        onHide={() => setShowDropModal(false)}
      />
    </div>
  );
}
