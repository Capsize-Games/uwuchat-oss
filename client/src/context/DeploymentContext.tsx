import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

// ── Types ─────────────────────────────────────────────────────────────────

export type DeploymentType = "edge" | "cloud";

interface DeploymentValue {
  deployment: DeploymentType;
  isEdge: boolean;
  isCloud: boolean;
  /** Override the deployment at runtime (persisted to localStorage). */
  setDeployment: (d: DeploymentType) => void;
}

// ── Build-time default & localStorage key ─────────────────────────────────

const BUILD_DEFAULT: DeploymentType = (
  import.meta.env.VITE_DEPLOYMENT as string | undefined
) === "cloud"
  ? "cloud"
  : "edge";

const LS_KEY = "airunner_deployment";

function loadOverride(): DeploymentType | null {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (raw === "edge" || raw === "cloud") return raw;
  } catch {
    // localStorage may be unavailable (private browsing)
  }
  return null;
}

function saveOverride(d: DeploymentType) {
  try {
    localStorage.setItem(LS_KEY, d);
  } catch {
    // silent
  }
}

// ── Context ───────────────────────────────────────────────────────────────

const DeploymentContext = createContext<DeploymentValue>({
  deployment: BUILD_DEFAULT,
  isEdge: BUILD_DEFAULT === "edge",
  isCloud: BUILD_DEFAULT === "cloud",
  setDeployment: () => {},
});

// ── Provider ──────────────────────────────────────────────────────────────

export function DeploymentProvider({
  children,
}: {
  children: ReactNode;
}) {
  const [deployment, setDeploymentState] =
    useState<DeploymentType>(
      () => loadOverride() ?? BUILD_DEFAULT,
    );

  // Keep localStorage in sync when the override changes
  useEffect(() => {
    saveOverride(deployment);
  }, [deployment]);

  const setDeployment = useCallback(
    (d: DeploymentType) => setDeploymentState(d),
    [],
  );

  const value = useMemo<DeploymentValue>(
    () => ({
      deployment,
      isEdge: deployment === "edge",
      isCloud: deployment === "cloud",
      setDeployment,
    }),
    [deployment, setDeployment],
  );

  return (
    <DeploymentContext.Provider value={value}>
      {children}
    </DeploymentContext.Provider>
  );
}

// ── Hook ──────────────────────────────────────────────────────────────────

export function useDeployment(): DeploymentValue {
  return useContext(DeploymentContext);
}

// ── Semantic wrapper components ───────────────────────────────────────────
// These are the ONLY place where isEdge / isCloud is checked in JSX.
// Consumers wrap edge-only / cloud-only JSX with these — no raw
// conditionals scattered through templates.

export function EdgeOnly({
  children,
}: {
  children: ReactNode;
}) {
  const { isEdge } = useDeployment();
  return isEdge ? <>{children}</> : null;
}

export function CloudOnly({
  children,
}: {
  children: ReactNode;
}) {
  const { isCloud } = useDeployment();
  return isCloud ? <>{children}</> : null;
}
