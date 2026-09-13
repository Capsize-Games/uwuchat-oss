import { request } from "@/api/client-base";

// ---- Types ---------------------------------------------------------------

export interface ItchioStatus {
  connected: boolean;
  status: "not_connected" | "connected" | "error";
  itch_user_id: number | null;
  username: string | null;
  display_name: string | null;
  cover_url: string | null;
  profile_url: string | null;
  owned_games: ItchioGame[];
  last_scraped_at: string | null;
  error: string | null;
}

export interface ItchioGame {
  appid: string;
  name: string;
  playtime_forever_minutes: null;
  playtime_2weeks_minutes: null;
  icon_url: string;
  source: "itchio";
  source_url: string | null;
}

// ---- Auth ----------------------------------------------------------------

export async function getItchAuthUrl(): Promise<string> {
  const res = await request<{ url: string }>(
    "GET",
    "/api/v1/itch/auth/login",
  );
  return res.url;
}

// ---- Status / Profile / Disconnect ---------------------------------------

export async function getItchStatus(
  userId: number,
): Promise<ItchioStatus> {
  return request<ItchioStatus>("GET", `/api/v1/itch/status/${userId}`);
}

export async function getItchProfile(
  userId: number,
): Promise<ItchioStatus> {
  return request<ItchioStatus>(
    "GET",
    `/api/v1/itch/profile/${userId}`,
  );
}

export async function disconnectItch(
  userId: number,
): Promise<{ success: boolean }> {
  return request<{ success: boolean }>(
    "POST",
    `/api/v1/itch/disconnect/${userId}`,
  );
}
