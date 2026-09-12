import { request } from "@/api/client-base";

// ---- Types ---------------------------------------------------------------

export interface SteamStatus {
  connected: boolean;
  status:
    | "not_connected"
    | "connected"
    | "error";
  steam_id: string | null;
  display_name: string | null;
  avatar_url: string | null;
  last_scraped_at: string | null;
  error: string | null;
  auth_provider: string | null;
}

export interface SteamGame {
  appid: number;
  name: string;
  playtime_forever_minutes: number;
  playtime_2weeks_minutes: number | null;
  icon_url: string;
  store_header_url: string | null;
  has_community_visible_stats: boolean;
  category: "played_recently" | "most_played" | "currently_playing";
}

export interface SteamProfile {
  user_id: number;
  steam_id: string;
  display_name: string;
  avatar_url: string | null;
  profile_url: string | null;
  persona_state: number | null;
  last_logoff: string | null;
  time_created: string | null;
  steam_level: number;
  total_games_owned: number;
  total_playtime_minutes: number;
  friend_count: number;
  owned_games: SteamGame[];
  all_games: SteamGame[];
  recently_played: SteamGame[];
}

export interface SteamAchievement {
  apiname: string;
  name: string;
  description: string;
  achieved: boolean;
  unlocktime: number;
  icon_url: string;
  icon_gray_url: string;
  global_percent: number | null;
}

export interface SteamAchievementsData {
  game_name: string;
  appid: number;
  achievements: SteamAchievement[];
  achieved_count: number;
  total_count: number;
  error?: string;
}

// ---- Auth ----------------------------------------------------------------

/**
 * Get the Steam OpenID login URL.
 * Call this, then redirect the browser to the returned URL.
 */
export async function getSteamAuthUrl(): Promise<string> {
  const res = await request<{ url: string }>(
    "GET",
    "/api/v1/steam/auth/login",
  );
  return res.url;
}

// ---- Status / Profile / Disconnect (via UwUchat backend) -----------------

/**
 * Get the Steam connection status for a user.
 */
export async function getSteamStatus(
  userId: number,
): Promise<SteamStatus> {
  return request<SteamStatus>(
    "GET",
    `/api/v1/steam/status/${userId}`,
  );
}

/**
 * Get the stored Steam profile for a user.
 */
export async function getSteamProfile(
  userId: number,
): Promise<SteamProfile | null> {
  try {
    return await request<SteamProfile>(
      "GET",
      `/api/v1/steam/profile/${userId}`,
    );
  } catch {
    return null;
  }
}

/**
 * Disconnect Steam account.
 */
export async function disconnectSteam(
  userId: number,
): Promise<{ success: boolean }> {
  return request<{ success: boolean }>(
    "POST",
    `/api/v1/steam/disconnect/${userId}`,
  );
}

/**
 * Re-check Steam connection status (rescrape is a no-op without FastSearch).
 */
export async function rescrapeSteam(
  userId: number,
): Promise<{ success: boolean }> {
  return request<{ success: boolean }>(
    "POST",
    `/api/v1/steam/rescrape/${userId}`,
  );
}

/**
 * Get achievements for a specific game.
 */
export async function getSteamAchievements(
  userId: number,
  appid: number,
): Promise<SteamAchievementsData> {
  return request<SteamAchievementsData>(
    "GET",
    `/api/v1/steam/achievements/${userId}?appid=${appid}`,
  );
}

/**
 * Refresh Steam profile data if stale (>4 hours).
 * Call on WebSocket connect or profile view.
 */
export async function refreshSteamData(): Promise<{
  refreshed: boolean;
  status: string;
}> {
  return request<{ refreshed: boolean; status: string }>(
    "POST",
    "/api/v1/steam/refresh",
  );
}

/**
 * Import Steam profile data (display name, avatar) into the user's profile.
 * Requires a linked Steam account and STEAM_API_KEY configured.
 */
export async function importSteamProfile(): Promise<{
  display_name: string;
  avatar_url: string;
}> {
  return request<{ display_name: string; avatar_url: string }>(
    "POST",
    "/api/v1/steam/import-profile",
  );
}
