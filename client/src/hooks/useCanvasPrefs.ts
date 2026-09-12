import { useState, useCallback } from "react";

// ── Raw localStorage helpers (no JSON encoding) ─────────────────────────

function getBool(key: string, fallback: boolean): boolean {
  try {
    const v = localStorage.getItem(key);
    if (v === null) return fallback;
    return v === "true";
  } catch {
    return fallback;
  }
}

function setBool(key: string, val: boolean): void {
  try {
    localStorage.setItem(key, String(val));
  } catch {
    /* quota */
  }
}

function setStr(key: string, val: string): void {
  try {
    localStorage.setItem(key, val);
  } catch {
    /* quota */
  }
}

function getNum(key: string, fallback: number): number {
  try {
    const v = localStorage.getItem(key);
    return v ? Number(v) : fallback;
  } catch {
    return fallback;
  }
}

function setNum(key: string, val: number): void {
  try {
    localStorage.setItem(key, String(val));
  } catch {
    /* quota */
  }
}

// ── Keys ────────────────────────────────────────────────────────────────

const K = {
  fitToView: "canvas_fit_to_view",
  centerView: "canvas_center_view",
  assetTab: "canvas_asset_tab",
  showAssets: "canvas_show_assets",
  gridLocked: "canvas_grid_locked",
  genType: "canvas_gen_type",
  showImagePrompt: "canvas_show_image_prompt",
  showCanvasTools: "canvas_show_canvas_tools",
  leftPanelW: "airunner_left_panel_w",
  leftPanelCollapsed: "airunner_left_panel_collapsed",
} as const;

export type GenType = "txt2img" | "img2img" | "inpaint";
export type AssetTab = "layers" | "images";

// ── Initializers ────────────────────────────────────────────────────────

function initFitToView(): boolean {
  return getBool(K.fitToView, true);
}

function initCenterView(): boolean {
  return getBool(K.centerView, false);
}

function initAssetTab(): AssetTab | null {
  try {
    const v = localStorage.getItem(K.assetTab);
    if (v === "layers" || v === "images") return v;
    // "none" is the persisted hidden state — keep the panel closed on reload.
    if (v === "none") return null;
    return localStorage.getItem(K.showAssets) !== "false" ? "layers" : null;
  } catch {
    return "layers";
  }
}

function initGridLocked(): boolean {
  return getBool(K.gridLocked, false);
}

function initGenType(): GenType {
  try {
    return (localStorage.getItem(K.genType) as GenType) || "txt2img";
  } catch {
    return "txt2img";
  }
}

function initShowImagePrompt(): boolean {
  return getBool(K.showImagePrompt, false);
}

function initShowCanvasTools(): boolean {
  return getBool(K.showCanvasTools, true);
}

function initLeftPanelW(): number {
  return getNum(K.leftPanelW, 300);
}

function initLeftPanelCollapsed(): boolean {
  return getBool(K.leftPanelCollapsed, false);
}

// ── useCanvasPrefs ──────────────────────────────────────────────────────
// Centralized access to canvas-panel localStorage preferences.
// All canvas-panel localStorage reads/writes MUST go through this hook.

export function useCanvasPrefs() {
  const [fitToView, setFitToViewState] = useState(initFitToView);
  const [centerView, setCenterViewState] = useState(initCenterView);
  const [assetTab, setAssetTabState] = useState<AssetTab | null>(initAssetTab);
  const [gridLocked, setGridLockedState] = useState(initGridLocked);
  const [genType, setGenTypeState] = useState<GenType>(initGenType);
  const [showImagePrompt, setShowImagePromptState] = useState(
    initShowImagePrompt,
  );
  const [showCanvasTools, setShowCanvasToolsState] = useState(
    initShowCanvasTools,
  );
  const [leftPanelW, setLeftPanelWState] = useState(initLeftPanelW);
  const [leftPanelCollapsed, setLeftPanelCollapsedState] = useState(
    initLeftPanelCollapsed,
  );

  // ── Persist on change ───────────────────────────────────────────────

  const setFitToView = useCallback((v: boolean) => {
    setBool(K.fitToView, v);
    setFitToViewState(v);
  }, []);

  const setCenterView = useCallback((v: boolean) => {
    setBool(K.centerView, v);
    setCenterViewState(v);
  }, []);

  const setAssetTab = useCallback((tab: AssetTab | null) => {
    setStr(K.assetTab, tab ?? "none");
    setAssetTabState(tab);
  }, []);

  const setGridLocked = useCallback((v: boolean) => {
    setBool(K.gridLocked, v);
    setGridLockedState(v);
  }, []);

  const setGenType = useCallback((v: GenType) => {
    setStr(K.genType, v);
    setGenTypeState(v);
  }, []);

  const setShowImagePrompt = useCallback((v: boolean) => {
    setBool(K.showImagePrompt, v);
    setShowImagePromptState(v);
  }, []);

  const setShowCanvasTools = useCallback((v: boolean) => {
    setBool(K.showCanvasTools, v);
    setShowCanvasToolsState(v);
  }, []);

  const setLeftPanelW = useCallback((w: number) => {
    setNum(K.leftPanelW, w);
    setLeftPanelWState(w);
  }, []);

  const setLeftPanelCollapsed = useCallback((v: boolean) => {
    setBool(K.leftPanelCollapsed, v);
    setLeftPanelCollapsedState(v);
  }, []);

  return {
    fitToView,
    setFitToView,
    centerView,
    setCenterView,
    assetTab,
    setAssetTab,
    gridLocked,
    setGridLocked,
    genType,
    setGenType,
    showImagePrompt,
    setShowImagePrompt,
    showCanvasTools,
    setShowCanvasTools,
    leftPanelW,
    setLeftPanelW,
    leftPanelCollapsed,
    setLeftPanelCollapsed,
  };
}
