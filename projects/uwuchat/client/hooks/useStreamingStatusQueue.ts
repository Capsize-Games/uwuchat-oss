import { useEffect, useRef, useState } from "react";

/* ── Shared types ──────────────────────────────────────────── */

export interface ToolStatusEvent {
  tool_id: string;
  tool_name: string;
  status: "starting" | "completed" | "error";
  details?: string | null;
}

export interface StatusDisplay {
  statusKey: string;
  iconName: string;
  label: string;
}

/* ── Tool-name → user-facing label/icon maps (shared source of truth) ── */

export const TOOL_LABELS: Record<string, string> = {
  search_fastsearch: "Searching internet",
  search_news: "Searching news",
  search_knowledge_base_documents: "Searching knowledge base",
  scrape_website: "Reading website",
  check_grounding: "Checking facts",
  update_mood: "Setting mood",
  block_user: "Blocking user",
  go_offline: "Going offline",
  list_tool_categories: "Analyzing request",
  switch_tool_category: "Switching tools",
};

export const TOOL_ICONS: Record<string, string> = {
  search_fastsearch: "globe",
  search_news: "newspaper",
  search_knowledge_base_documents: "database",
  scrape_website: "link",
  check_grounding: "shield-check",
  update_mood: "sparkles",
  block_user: "circle-x",
  go_offline: "cloud-fog",
  list_tool_categories: "sliders-horizontal",
  switch_tool_category: "shuffle",
};

/* ── Pure derivation helpers (shared) ──────────────────────── */

function toolActivity(tool: ToolStatusEvent): string {
  if (tool.details) return tool.details;
  const label = TOOL_LABELS[tool.tool_name] ?? tool.tool_name.replace(/_/g, " ");
  return label.charAt(0).toUpperCase() + label.slice(1);
}

function currentTool(activeTools: ToolStatusEvent[]): ToolStatusEvent | null {
  const running = activeTools.find((t) => t.status === "starting");
  if (running) return running;
  if (activeTools.length > 0) {
    return activeTools[activeTools.length - 1];
  }
  return null;
}

/**
 * Derive the desired status from raw inputs, using the same priority
 * order as the original StreamingStatus component:
 * showTyping → active tool → thinking → "preparing".
 */
export function computeDesiredStatus(
  activeTools: ToolStatusEvent[],
  thinkingBuffer: string,
  isThinking: boolean,
  showTyping: boolean,
): StatusDisplay {
  if (showTyping) {
    return { statusKey: "reading", iconName: "book-open", label: "Reading" };
  }

  const tool = currentTool(activeTools);
  if (tool) {
    return {
      statusKey: `tool-${tool.tool_name}`,
      iconName: TOOL_ICONS[tool.tool_name] ?? "wrench",
      label: toolActivity(tool),
    };
  }

  if (isThinking || thinkingBuffer.length > 0) {
    return { statusKey: "thinking", iconName: "brain", label: "Thinking" };
  }

  return { statusKey: "preparing", iconName: "sparkles", label: "Preparing" };
}

/**
 * Returns true when the status represents an actual running activity
 * (tool execution, thinking, immersion reading) rather than the idle
 * "preparing" fallback.
 */
export function statusHasActivity(display: StatusDisplay): boolean {
  return display.statusKey !== "preparing";
}

/* ── Constants ─────────────────────────────────────────────── */

const MIN_STATUS_HOLD_MS = 900;

/* ── Hook ──────────────────────────────────────────────────── */

interface UseStreamingStatusQueueResult {
  /** The stabilized status to display. */
  statusKey: string;
  iconName: string;
  label: string;
  /** True when the status represents an actual running activity. */
  hasActivity: boolean;
}

/**
 * Stabilizes status transitions so each status is held on screen for
 * at least `MIN_STATUS_HOLD_MS` before advancing to the next one.
 *
 * The very first status of a new tool-call sequence appears
 * immediately with no artificial delay.
 *
 * When tool activity fully finishes, the hook resets its internal
 * state so stale statuses don't bleed into the next message.
 */
export function useStreamingStatusQueue(
  activeTools: ToolStatusEvent[],
  thinkingBuffer: string,
  isThinking: boolean,
  showTyping: boolean,
): UseStreamingStatusQueueResult {
  const initialDisplay = computeDesiredStatus(
    activeTools,
    thinkingBuffer,
    isThinking,
    showTyping,
  );

  const [displayed, setDisplayed] = useState<StatusDisplay>(initialDisplay);
  const committedAtRef = useRef(0); // 0 means "never committed" → first status is immediate
  const pendingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const latestDesiredRef = useRef<StatusDisplay>(initialDisplay);

  useEffect(() => {
    const desired = computeDesiredStatus(
      activeTools,
      thinkingBuffer,
      isThinking,
      showTyping,
    );
    latestDesiredRef.current = desired;

    // Same status → nothing to do.
    if (desired.statusKey === displayed.statusKey) return;

    const commit = (value: StatusDisplay) => {
      if (pendingTimeoutRef.current !== null) {
        clearTimeout(pendingTimeoutRef.current);
        pendingTimeoutRef.current = null;
      }
      setDisplayed(value);
      committedAtRef.current = Date.now();
    };

    const elapsed = Date.now() - committedAtRef.current;

    // First-ever status (committedAtRef is 0) or enough time has passed.
    if (committedAtRef.current === 0 || elapsed >= MIN_STATUS_HOLD_MS) {
      commit(desired);
      return;
    }

    // Hold remaining — schedule a commit with the latest desired value.
    if (pendingTimeoutRef.current !== null) {
      clearTimeout(pendingTimeoutRef.current);
    }
    const remaining = MIN_STATUS_HOLD_MS - elapsed;
    pendingTimeoutRef.current = setTimeout(() => {
      commit(latestDesiredRef.current);
    }, remaining);
  }, [activeTools, thinkingBuffer, isThinking, showTyping, displayed.statusKey]);

  // Cleanup on unmount.
  useEffect(() => {
    return () => {
      if (pendingTimeoutRef.current !== null) {
        clearTimeout(pendingTimeoutRef.current);
      }
    };
  }, []);

  // Reset internal state when activity fully finishes.
  // "Fully finished" means no active tools, no thinking buffer, not thinking,
  // and not showing typing.
  const isIdle =
    activeTools.length === 0 &&
    thinkingBuffer.length === 0 &&
    !isThinking &&
    !showTyping;

  useEffect(() => {
    if (isIdle && displayed.statusKey !== "preparing") {
      if (pendingTimeoutRef.current !== null) {
        clearTimeout(pendingTimeoutRef.current);
        pendingTimeoutRef.current = null;
      }
      // Reset to "preparing" immediately with no hold constraint.
      const idle = computeDesiredStatus([], "", false, false);
      latestDesiredRef.current = idle;
      setDisplayed(idle);
      committedAtRef.current = 0;
    }
  }, [isIdle, displayed.statusKey]);

  return {
    statusKey: displayed.statusKey,
    iconName: displayed.iconName,
    label: displayed.label,
    hasActivity: statusHasActivity(displayed),
  };
}
