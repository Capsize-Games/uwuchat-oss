/**
 * Admin API for forcing a proactive message from a chatbot.
 * Only callable by superuser accounts.
 */

import { BASE_URL } from "../types/api";

export async function forceProactiveMessage(
  chatbotId: number,
  accessToken: string,
): Promise<void> {
  const res = await fetch(`${BASE_URL}/api/v1/llm/proactive-trigger`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({ chatbot_id: chatbotId }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(
      (body as Record<string, string>).detail ?? `HTTP ${res.status}`,
    );
  }
}
