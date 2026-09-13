/** Admin API client for the conversation event audit log. */

import { request } from "@/api/client-base";

export interface ConversationEvent {
  event_id: string;
  event_type: string;
  actor: string;
  payload: Record<string, unknown>;
  created_at: string;
  sequence_num: number | null;
  conversation_id: number | null;
  session_id: number | null;
}

export async function listAdminEvents(
  chatbotId: number,
  params?: {
    since?: string;
    until?: string;
    event_types?: string;
    limit?: number;
    offset?: number;
  },
): Promise<{ events: ConversationEvent[]; total: number }> {
  const body: Record<string, unknown> = { chatbot_id: chatbotId };
  if (params?.since) body.since = params.since;
  if (params?.until) body.until = params.until;
  if (params?.event_types) body.event_types = params.event_types;
  if (params?.limit !== undefined) body.limit = params.limit;
  if (params?.offset !== undefined) body.offset = params.offset;
  return request<{ events: ConversationEvent[]; total: number }>(
    "GET",
    "/api/v1/admin/events",
    body,
  );
}

export async function getEventContext(
  eventId: string,
): Promise<{
  before: ConversationEvent[];
  after: ConversationEvent[];
  projected_state: unknown[];
}> {
  return request<{
    before: ConversationEvent[];
    after: ConversationEvent[];
    projected_state: unknown[];
  }>("GET", `/api/v1/admin/events/${eventId}/context`);
}

/** Issue a Stripe refund for an account (superuser only).
 *
 * The endpoint initiates the refund in Stripe; the resulting
 * ``charge.refunded`` webhook is what actually updates the
 * Account billing fields — manual dashboard refunds and
 * API-initiated refunds behave identically.
 */
