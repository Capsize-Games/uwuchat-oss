import { request } from "./client-base";

export interface Post {
  id: number;
  content: string;
  created_at: string;
  visibility: "public" | "followers";
}

export async function getChatbotPosts(
  chatbotId: number,
  limit = 20,
): Promise<Post[]> {
  return request<Post[]>(
    "GET",
    `/api/v1/chatbots/${chatbotId}/posts?limit=${limit}`,
  );
}
