/**
 * itch.io OAuth callback page.
 *
 * itch.io uses OAuth implicit grant — the access_token and state are
 * returned in the URL fragment (#access_token=...&state=...).
 * Browsers do NOT send fragments to the server.  This page extracts
 * them client-side and POSTs the token to the backend in the request
 * body so it never lands in server/proxy access logs as a URL query
 * parameter.
 */

import { useEffect } from "react";
import styles from "./ItchioCallbackPage.module.css";

async function _exchangeToken(
  state: string,
  token: string,
): Promise<{ ok: boolean; error?: string }> {
  try {
    const resp = await fetch("/api/v1/itch/auth/callback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        state,
        access_token: token,
      }),
    });
    if (resp.redirected) {
      // The backend returned a redirect — follow it client-side.
      window.location.replace(resp.url);
      return { ok: true };
    }
    if (!resp.ok) {
      return { ok: false, error: `server_error_${resp.status}` };
    }
    return { ok: true };
  } catch {
    return { ok: false, error: "network_error" };
  }
}

export default function ItchioCallbackPage() {
  useEffect(() => {
    const hash = window.location.hash.substring(1);
    const params = new URLSearchParams(hash);
    const token = params.get("access_token");
    const state = params.get("state");

    if (!token || !state) {
      window.location.replace(
        "/settings?tab=integrations&itch_error=no_token",
      );
      return;
    }

    _exchangeToken(state, token).then((result) => {
      if (result.ok) return;
      window.location.replace(
        `/settings?tab=integrations&itch_error=${result.error || "exchange_failed"}`,
      );
    });
  }, []);

  return (
    <div className={styles.wrap}>
      Connecting itch.io…
    </div>
  );
}
