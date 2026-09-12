import { request } from "@/api/client-base";

// ---- Types ---------------------------------------------------------------

export interface BlueskyPost {
  uri: string;
  cid: string;
  text: string;
  createdAt: string;
  likeCount: number;
  repostCount: number;
  replyCount: number;
  embed?: BlueskyEmbed;
}

interface BlueskyEmbed {
  $type: string;
  images?: BlueskyImage[];
}

interface BlueskyImage {
  thumb: string;
  fullsize: string;
  alt: string;
}

export interface BlueskyStatus {
  connected: boolean;
  status: "not_connected" | "connected" | "error";
  handle: string | null;
  did: string | null;
  error: string | null;
}

export interface BlueskyPostsResponse {
  posts: BlueskyPost[];
  handle: string | null;
}

// ---- App Password Connect ------------------------------------------------

/**
 * Connect a Bluesky account using handle + app password.
 * App passwords are generated at https://bsky.social/settings/app-passwords
 */
export async function connectBluesky(
  userId: number,
  handle: string,
  appPassword: string,
): Promise<{ connected: boolean; handle: string; did: string }> {
  return request<{ connected: boolean; handle: string; did: string }>(
    "POST",
    `/api/v1/bluesky/connect/${userId}`,
    { handle, app_password: appPassword },
  );
}

// ---- Status / Posts / Disconnect -----------------------------------------

export async function getBlueskyStatus(
  userId: number,
): Promise<BlueskyStatus> {
  return request<BlueskyStatus>(
    "GET",
    `/api/v1/bluesky/status/${userId}`,
  );
}

export async function getBlueskyPosts(
  userId: number,
): Promise<BlueskyPostsResponse> {
  return request<BlueskyPostsResponse>(
    "GET",
    `/api/v1/bluesky/posts/${userId}`,
  );
}

export async function disconnectBluesky(
  userId: number,
): Promise<{ success: boolean }> {
  return request<{ success: boolean }>(
    "POST",
    `/api/v1/bluesky/disconnect/${userId}`,
  );
}
