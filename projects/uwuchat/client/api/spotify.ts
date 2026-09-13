import { request } from "./client-base";

// ── Types ────────────────────────────────────────────────────────────────

export interface SpotifyImage {
  url: string;
  height: number;
  width: number;
}

export interface SpotifyArtistRef {
  id: string;
  name: string;
  spotify_url: string;
}

export interface SpotifyArtist {
  id: string;
  name: string;
  genres: string[];
  images: SpotifyImage[];
  rank: number;
  popularity: number;
  followers_count: number;
  spotify_url: string;
}

export interface SpotifyTrack {
  id: string;
  name: string;
  artists: SpotifyArtistRef[];
  album_name: string;
  album_images: SpotifyImage[];
  rank: number;
  duration_ms: number;
  popularity: number;
  preview_url: string | null;
  spotify_url: string;
}

export interface SpotifyPlaylist {
  id: string;
  name: string;
  description: string | null;
  images: SpotifyImage[];
  tracks_count: number;
  is_public: boolean;
  is_collaborative: boolean;
  owner_name: string;
  spotify_url: string;
}

export interface SpotifyRecentlyPlayedItem {
  track: {
    id: string;
    name: string;
    artists: SpotifyArtistRef[];
    album_name: string;
    album_images: SpotifyImage[];
    spotify_url: string;
    preview_url: string | null;
  };
  played_at: string;
}

export interface SpotifyGenreSummary {
  top_genres: { genre: string; count: number }[];
}

export interface SpotifyProfile {
  user_id: number;
  spotify_user_id: string;
  display_name: string;
  images: SpotifyImage[];
  followers_count: number;
  country: string | null;
  product: string;
  top_artists_short: SpotifyArtist[];
  top_artists_medium: SpotifyArtist[];
  top_artists_long: SpotifyArtist[];
  top_tracks_short: SpotifyTrack[];
  top_tracks_medium: SpotifyTrack[];
  top_tracks_long: SpotifyTrack[];
  playlists: SpotifyPlaylist[];
  saved_tracks_count: number;
  recently_played: SpotifyRecentlyPlayedItem[];
  followed_artists_count: number;
  genre_summary: SpotifyGenreSummary;
  last_scraped_at: string;
}

export interface SpotifyStatus {
  connected: boolean;
  status:
    | "not_connected"
    | "pending"
    | "scraping"
    | "complete"
    | "error";
  spotify_user_id: string | null;
  display_name: string | null;
  spotify_image_url: string | null;
  last_scraped_at: string | null;
  error: string | null;
}

// ── Configuration ────────────────────────────────────────────────────────

const FS_BASE = import.meta.env.VITE_FASTSEARCH_BASE_URL || "";

function fsUrl(path: string): string {
  return `${FS_BASE}${path}`;
}

// ── API Functions ────────────────────────────────────────────────────────

/**
 * Get the Spotify connection status for a user.
 * Poll this after linking to check when scraping completes.
 */
export async function getSpotifyStatus(
  userId: number,
): Promise<SpotifyStatus> {
  return request<SpotifyStatus>(
    "GET",
    fsUrl(`/api/v1/spotify/status/${userId}`),
  );
}

/**
 * Get the full scraped Spotify profile for a user.
 */
export async function getSpotifyProfile(
  userId: number,
): Promise<SpotifyProfile | null> {
  try {
    return await request<SpotifyProfile>(
      "GET",
      fsUrl(`/api/v1/spotify/profile/${userId}`),
    );
  } catch {
    return null;
  }
}

/**
 * Disconnect Spotify and delete all stored data.
 */
export async function disconnectSpotify(
  userId: number,
): Promise<{ success: boolean }> {
  return request<{ success: boolean }>(
    "POST",
    fsUrl(`/api/v1/spotify/disconnect/${userId}`),
  );
}

/**
 * Generate a signed state JWT for the Spotify OAuth flow.
 * The server signs the PKCE code_verifier into a JWT that
 * FastSearch validates on the callback.
 */
export async function generateSpotifyState(
  codeVerifier: string,
): Promise<string> {
  const res = await request<{ state: string }>(
    "POST",
    "/api/v1/spotify/generate-state",
    { code_verifier: codeVerifier },
  );
  return res.state;
}

/**
 * Trigger a fresh data re-scrape.
 */
export async function rescrapeSpotify(
  userId: number,
): Promise<{ success: boolean }> {
  return request<{ success: boolean }>(
    "POST",
    fsUrl(`/api/v1/spotify/rescrape/${userId}`),
  );
}