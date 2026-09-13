import { request } from "@/api/client-base";

export interface UserProfile {
  id: number;
  username: string | null;
  display_name: string | null;
  gender: string | null;
  latitude: number | null;
  longitude: number | null;
  location_display_name: string | null;
  unit_system: string | null;
  preferred_language: string | null;
  setup_complete: boolean | null;
  /** Arbitrary JSON data blob (social_links, preferences, etc.). */
  data: Record<string, unknown> | null;
  /** Base64-encoded profile avatar image. */
  avatar_image: string | null;
  /** Base64-encoded profile banner image. */
  banner_image: string | null;
}

/** Upload a profile avatar or banner image as base64. */
export async function uploadProfileImage(
  type: "avatar" | "banner",
  image: string,
): Promise<string | null> {
  try {
    const res = await request<{ avatar_image?: string; banner_image?: string }>(
      "POST",
      "/api/v1/user/profile-image",
      { type, image },
    );
    return res?.avatar_image ?? res?.banner_image ?? null;
  } catch {
    return null;
  }
}

export interface GeocodeResult {
  lat: number;
  lon: number;
  display_name: string;
}

export async function getUser(): Promise<UserProfile | null> {
  try {
    const res = await request<{ record: UserProfile }>(
      "GET",
      "/api/v1/settings/resources/User/singleton",
    );
    return res.record ?? null;
  } catch {
    return null;
  }
}

export async function updateUser(
  values: Partial<UserProfile>,
): Promise<UserProfile | null> {
  try {
    const res = await request<UserProfile>(
      "PUT",
      "/api/v1/settings/resources/User/singleton",
      { values },
    );
    return res ?? null;
  } catch {
    return null;
  }
}

export async function geocodeCity(
  city: string,
  country: string,
): Promise<GeocodeResult | null> {
  try {
    const res = await request<{ lat: number; lon: number; display_name: string }>(
      "POST",
      "/api/v1/geocode/city",
      { city, country },
    );
    return res ?? null;
  } catch {
    return null;
  }
}

export interface ReverseGeocodeResult {
  display_name: string;
}

export async function reverseGeocode(
  lat: number,
  lon: number,
): Promise<ReverseGeocodeResult | null> {
  try {
    const res = await request<{ display_name: string }>(
      "POST",
      "/api/v1/geocode/reverse",
      { lat, lon },
    );
    return res ?? null;
  } catch {
    return null;
  }
}

export interface ForecastDay {
  date: string;
  weather_code: number;
  weather_label: string;
  temperature_max: number | null;
  temperature_min: number | null;
  precipitation_sum: number;
  precipitation_probability: number | null;
  wind_speed_max: number | null;
  temperature_unit: string;
  wind_speed_unit: string;
}

export interface HourlyData {
  /** "HH:MM" local time string. */
  time: string;
  temperature: number;
  apparent_temperature: number;
  weather_code: number;
  weather_label: string;
  precipitation: number;
  precipitation_probability: number;
  wind_speed: number;
  humidity: number;
  temperature_unit: string;
  wind_speed_unit: string;
}

export interface WeatherData {
  /** Human-readable location name (e.g. "Denver, Colorado, United States"). */
  location: string;
  /** ISO 8601 UTC timestamp when the cache entry was created. */
  cached_at: string;
  /** Seconds until the server cache expires (always 3600). */
  cache_ttl: number;
  temperature: number;
  apparent_temperature: number;
  humidity: number;
  weather_code: number;
  weather_label: string;
  is_day: number;
  cloud_cover: number;
  uv_index: number;
  precipitation: number;
  rain: number;
  showers: number;
  snowfall: number;
  wind_speed: number;
  wind_direction: number;
  wind_gusts: number;
  temperature_unit: string;
  wind_speed_unit: string;
  precipitation_unit: string;
  forecast: ForecastDay[];
  /** Today's hourly forecast (filtered from full Open-Meteo set). */
  hourly: HourlyData[];
}

/** Fetch current weather and 10-day forecast. */
export async function fetchWeather(): Promise<WeatherData> {
  return request<WeatherData>("GET", "/api/v1/weather");
}
