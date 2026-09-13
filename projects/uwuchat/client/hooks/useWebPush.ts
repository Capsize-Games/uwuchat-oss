import { useEffect, useState } from "react";
import { request } from "../api/client-base";

async function getVapidKey(): Promise<string | null> {
  try {
    const res = await request<{ public_key: string }>(
      "GET",
      "/api/v1/push/vapid-public-key",
    );
    return res.public_key ?? null;
  } catch {
    return null;
  }
}

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding)
    .replace(/-/g, "+")
    .replace(/_/g, "/");
  const rawData = atob(base64);
  return Uint8Array.from([...rawData].map((c) => c.charCodeAt(0)));
}

async function subscribeToPush(
  vapidKey: string,
  accountId: number,
): Promise<boolean> {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    return false;
  }
  try {
    const reg = await navigator.serviceWorker.ready;
    const existing = await reg.pushManager.getSubscription();
    const sub =
      existing ??
      (await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(vapidKey),
      }));
    const json = sub.toJSON();
    const keys = json.keys as { p256dh: string; auth: string } | undefined;
    if (!json.endpoint || !keys?.p256dh || !keys?.auth) return false;
    await request("POST", "/api/v1/push/subscribe", {
      endpoint: json.endpoint,
      keys: { p256dh: keys.p256dh, auth: keys.auth },
      account_id: accountId,
    });
    return true;
  } catch {
    return false;
  }
}

export function useWebPush(accountId: number | null): {
  supported: boolean;
  subscribed: boolean;
  subscribe: () => Promise<void>;
} {
  const [supported, setSupported] = useState(false);
  const [subscribed, setSubscribed] = useState(false);

  useEffect(() => {
    setSupported(
      "serviceWorker" in navigator && "PushManager" in window,
    );
  }, []);

  async function subscribe() {
    if (!accountId) return;
    const key = await getVapidKey();
    if (!key) return;
    const ok = await subscribeToPush(key, accountId);
    if (ok) setSubscribed(true);
  }

  return { supported, subscribed, subscribe };
}
