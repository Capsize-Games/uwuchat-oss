import { type ReactNode } from "react";
import styles from "./IntegrationCard.module.css";

export interface IntegrationCardProps {
  name: string;
  icon: ReactNode;
  description: string;
  loading: boolean;
  connected: boolean;
  error?: string | null;
  onConnect: () => void;
  onDisconnect: () => void;
  /* ── New optional props ────────────────────── */
  connecting?: boolean;
  disconnecting?: boolean;
  connectLabel?: string;
  connectedLabel?: string;
  statusText?: string | null;
  showDisconnect?: boolean;
}

export function IntegrationCard({
  name,
  icon,
  description,
  loading,
  connected,
  error,
  onConnect,
  onDisconnect,
  connecting = false,
  disconnecting = false,
  connectLabel = "Connect",
  connectedLabel,
  statusText = null,
  showDisconnect = true,
}: IntegrationCardProps) {
  const disabled = loading || connecting || disconnecting;

  // When connected and showDisconnect is suppressed, render as a
  // non-interactive card (e.g. Steam when auth_provider is already Steam).
  const interactive = !(connected && !showDisconnect);

  const label = connected
    ? disconnecting
      ? "Disconnecting…"
      : "Disconnect"
    : connecting
      ? "Connecting…"
      : connectLabel;

  const labelCls = connected ? styles.disconnectLabel : styles.connectLabel;

  const inner = (
    <>
      <div className={styles.header}>
        <span className={styles.icon}>{icon}</span>
        <div className={styles.info}>
          <div className={styles.name}>{name}</div>
          <div className={styles.desc}>{description}</div>
        </div>
        {connected ? (
          <span className={styles.connected}>
            {connectedLabel ?? "Connected"}
          </span>
        ) : (
          <span className={styles.off}>Not connected</span>
        )}
      </div>
      {statusText != null && (
        <div className={styles.statusText}>{statusText}</div>
      )}
      {loading && <div className={styles.loading}>Checking status…</div>}
      {error && <div className={styles.error}>{error}</div>}
      <span className={labelCls}>{label}</span>
    </>
  );

  if (!interactive) {
    return <div className={styles.card}>{inner}</div>;
  }

  return (
    <button
      type="button"
      className={styles.card}
      onClick={connected ? onDisconnect : onConnect}
      disabled={disabled}
    >
      {inner}
    </button>
  );
}
