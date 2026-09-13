import { request } from "./client-base";

export interface ChatbotStatus {
  is_online: boolean;
  offline_until: string | null;
  has_blocked_user: boolean;
  blocked_by_user: boolean;
}

export async function getChatbotStatus(
  chatbotId: number,
): Promise<ChatbotStatus> {
  return request<ChatbotStatus>(
    "GET",
    `/api/v1/chatbots/${chatbotId}/status`,
  );
}

export async function blockChatbot(chatbotId: number): Promise<void> {
  await request("POST", `/api/v1/chatbots/${chatbotId}/block`, {});
}

export async function unblockChatbot(chatbotId: number): Promise<void> {
  await request("DELETE", `/api/v1/chatbots/${chatbotId}/block`, {});
}

export interface ReportChatbotMessageRequest {
  message_id?: number;
  reason: string;
  detail?: string;
}

export interface ReportChatbotMessageResponse {
  status: string;
}

export async function reportChatbotMessage(
  chatbotId: number,
  body: ReportChatbotMessageRequest,
): Promise<ReportChatbotMessageResponse> {
  return request<ReportChatbotMessageResponse>(
    "POST",
    `/api/v1/chatbots/${chatbotId}/report`,
    body as unknown as Record<string, unknown>,
  );
}

export interface OmnipotentKnowledgeResponse {
  omnipotent_knowledge: boolean;
}

export async function toggleOmnipotentKnowledge(
  chatbotId: number,
  enabled: boolean,
): Promise<OmnipotentKnowledgeResponse> {
  return request<OmnipotentKnowledgeResponse>(
    "POST",
    `/api/v1/chatbots/${chatbotId}/omnipotent-knowledge`,
    { enabled },
  );
}
