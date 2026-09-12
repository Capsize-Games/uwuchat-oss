// ── Live Indicator ──────────────────────────────────────────────────────
import { useState, useEffect } from "react";
import {
  isWsConnected,
  onWsConnectionChange,
} from "../../features/api/WsApiClient";
import styles from "./LiveIndicator.module.css";

export default function LiveIndicator() {
  const [connected, setConnected] =
    useState(isWsConnected);
  useEffect(() => {
    // Sync once in case the state changed between render and effect, then
    // update on pushed connect/disconnect transitions (no polling).
    setConnected(isWsConnected());
    return onWsConnectionChange(setConnected);
  }, []);
  return (
    <span
      className={styles.label}
      // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
      style={{
        color: connected
          ? "rgba(0,200,100,0.7)"
          : "rgba(255,150,50,0.6)",
      }}
    >
      <span
        className={styles.dot}
        // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
        style={{
          background: connected
            ? "rgb(0,200,100)"
            : "rgb(255,150,50)",
        }}
      />
      {connected ? "Live" : "Reconnecting…"}
    </span>
  );
}
