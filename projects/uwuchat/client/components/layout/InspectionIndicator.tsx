import { useEffect, useState, useCallback } from "react";
import LucideIcon from "@/components/shared/LucideIcon";
import { useAuth } from "../../hooks/useAuth";
import styles from "./InspectionIndicator.module.css";

export default function InspectionIndicator() {
  const { user } = useAuth();
  const isSuperuser = user?.is_superuser === true;
  const [enabled, setEnabled] = useState(false);
  const handleChange = useCallback((e: Event) => { const d = (e as CustomEvent<{ enabled: boolean }>).detail; if (d && typeof d.enabled === "boolean") setEnabled(d.enabled); }, []);
  useEffect(() => { window.addEventListener("airunner:inspection-changed", handleChange); return () => window.removeEventListener("airunner:inspection-changed", handleChange); }, [handleChange]);
  if (!isSuperuser) return null;
  const color = enabled ? "#4caf50" : "rgba(255,255,255,0.35)";
  // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
  return <div className={styles.dot} style={{ background: color }} title={enabled ? "Inspection on" : "Inspection off"} />;
}
