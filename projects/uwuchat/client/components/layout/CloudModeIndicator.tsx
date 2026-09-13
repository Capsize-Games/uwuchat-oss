import { useDeployment } from "@/context/DeploymentContext";
import LucideIcon from "@/components/shared/LucideIcon";
import { useAuth } from "../../hooks/useAuth";
import styles from "./CloudModeIndicator.module.css";

export default function CloudModeIndicator() {
  const { user } = useAuth();
  const isSuperuser = user?.is_superuser === true;
  const { deployment, setDeployment } = useDeployment();
  if (!isSuperuser) return null;
  const isCloud = deployment === "cloud";
  const color = isCloud ? "#4caf50" : "rgba(255,255,255,0.35)";
  // eslint-disable-next-line no-restricted-syntax -- computed dimension from state/prop
  return <button onClick={() => setDeployment(isCloud ? "edge" : "cloud")} className={`${styles.wrap} d-flex`} style={{ color }} title={isCloud ? "Cloud mode" : "Edge mode"}><LucideIcon name="cloud" size={15} color={color} /></button>;
}
