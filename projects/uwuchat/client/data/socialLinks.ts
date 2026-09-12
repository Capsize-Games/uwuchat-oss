/**
 * Social media link service definitions for UwUchat profiles.
 *
 * The User model stores links in User.data.social_links as:
 *   { [serviceKey]: "username_or_url", ... }
 *
 * Only services listed in ALL_SERVICES are recognized for display.
 * Unknown keys in stored data are silently ignored.
 */

// ── Types ────────────────────────────────────────────────────────────────

/** A single social link service definition. */
export interface SocialService {
  /** Unique key used in the JSON blob (e.g. "twitter"). */
  key: string;
  /** Human-readable label shown in the UI. */
  label: string;
  /**
   * URL builder. Receives the stored value and returns a full URL.
   * If the stored value is already a full URL (http/https), it is
   * returned as-is. Otherwise the value is treated as a username
   * and interpolated into the base URL.
   */
  baseUrl: string;
  /** Accent color for the service badge (CSS color string). */
  color: string;
  /** Category for grouping in the settings UI. */
  category: SocialCategory;
}

export type SocialCategory =
  | "social"
  | "creative"
  | "gaming"
  | "music"
  | "writing"
  | "support"
  | "professional"
  | "other";

export const CATEGORY_LABELS: Record<SocialCategory, string> = {
  social: "Social",
  creative: "Creative",
  gaming: "Gaming",
  music: "Music & Audio",
  writing: "Writing & Blogs",
  support: "Support Me",
  professional: "Professional",
  other: "Other",
};

/** Stored social links map: service key → value (username or full URL). */
export type SocialLinksMap = Record<string, string>;

// ── Helpers ──────────────────────────────────────────────────────────────

/** Build a full URL from a service definition and a stored value. */
export function buildSocialUrl(service: SocialService, value: string): string {
  if (/^https?:\/\//i.test(value)) {
    return value;
  }
  return service.baseUrl.replace("{}", encodeURIComponent(value));
}

/** Extract a username from a stored value (null if it's a full URL). */
export function extractUsername(
  service: SocialService,
  value: string,
): string | null {
  if (/^https?:\/\//i.test(value)) {
    try {
      const url = new URL(value);
      const path = url.pathname.replace(/\/+$/, "");
      const last = path.split("/").pop();
      return last && last.length > 0 ? last : null;
    } catch {
      return null;
    }
  }
  return value;
}

// ── All Services Registry ────────────────────────────────────────────────

export const ALL_SERVICES: SocialService[] = [
  // ── Social ───────────────────────────────────────────────────────────
  {
    key: "twitter",
    label: "X",
    baseUrl: "https://x.com/{}",
    color: "#000000",
    category: "social",
  },
  {
    key: "bluesky",
    label: "Bluesky",
    baseUrl: "https://bsky.app/profile/{}",
    color: "#1185FE",
    category: "social",
  },
  {
    key: "mastodon",
    label: "Mastodon",
    baseUrl: "https://{}",
    color: "#6364FF",
    category: "social",
  },
  {
    key: "threads",
    label: "Threads",
    baseUrl: "https://www.threads.net/@{}",
    color: "#000000",
    category: "social",
  },
  {
    key: "instagram",
    label: "Instagram",
    baseUrl: "https://instagram.com/{}",
    color: "#E4405F",
    category: "social",
  },
  {
    key: "facebook",
    label: "Facebook",
    baseUrl: "https://facebook.com/{}",
    color: "#1877F2",
    category: "social",
  },
  {
    key: "snapchat",
    label: "Snapchat",
    baseUrl: "https://snapchat.com/add/{}",
    color: "#FFFC00",
    category: "social",
  },
  {
    key: "tiktok",
    label: "TikTok",
    baseUrl: "https://tiktok.com/@{}",
    color: "#000000",
    category: "social",
  },
  {
    key: "reddit",
    label: "Reddit",
    baseUrl: "https://reddit.com/user/{}",
    color: "#FF4500",
    category: "social",
  },
  {
    key: "discord",
    label: "Discord",
    baseUrl: "https://discord.com/users/{}",
    color: "#5865F2",
    category: "social",
  },
  {
    key: "telegram",
    label: "Telegram",
    baseUrl: "https://t.me/{}",
    color: "#26A5E4",
    category: "social",
  },
  {
    key: "whatsapp",
    label: "WhatsApp",
    baseUrl: "https://wa.me/{}",
    color: "#25D366",
    category: "social",
  },
  {
    key: "signal",
    label: "Signal",
    baseUrl: "https://signal.group/#{}",
    color: "#3A76F0",
    category: "social",
  },
  {
    key: "pinterest",
    label: "Pinterest",
    baseUrl: "https://pinterest.com/{}",
    color: "#BD081C",
    category: "social",
  },
  {
    key: "tumblr",
    label: "Tumblr",
    baseUrl: "https://{}.tumblr.com",
    color: "#36465D",
    category: "social",
  },

  // ── Creative ──────────────────────────────────────────────────────────
  {
    key: "artstation",
    label: "ArtStation",
    baseUrl: "https://www.artstation.com/{}",
    color: "#13AFF0",
    category: "creative",
  },
  {
    key: "deviantart",
    label: "DeviantArt",
    baseUrl: "https://www.deviantart.com/{}",
    color: "#05CC47",
    category: "creative",
  },
  {
    key: "behance",
    label: "Behance",
    baseUrl: "https://www.behance.net/{}",
    color: "#1769FF",
    category: "creative",
  },
  {
    key: "dribbble",
    label: "Dribbble",
    baseUrl: "https://dribbble.com/{}",
    color: "#EA4C89",
    category: "creative",
  },
  {
    key: "vimeo",
    label: "Vimeo",
    baseUrl: "https://vimeo.com/{}",
    color: "#1AB7EA",
    category: "creative",
  },

  // ── Gaming ────────────────────────────────────────────────────────────
  {
    key: "twitch",
    label: "Twitch",
    baseUrl: "https://twitch.tv/{}",
    color: "#9146FF",
    category: "gaming",
  },
  {
    key: "youtube",
    label: "YouTube",
    baseUrl: "https://youtube.com/@{}",
    color: "#FF0000",
    category: "gaming",
  },
  {
    key: "steam",
    label: "Steam",
    baseUrl: "https://steamcommunity.com/id/{}",
    color: "#000000",
    category: "gaming",
  },

  // ── Music & Audio ─────────────────────────────────────────────────────
  {
    key: "soundcloud",
    label: "SoundCloud",
    baseUrl: "https://soundcloud.com/{}",
    color: "#FF5500",
    category: "music",
  },
  {
    key: "bandcamp",
    label: "Bandcamp",
    baseUrl: "https://{}.bandcamp.com",
    color: "#629AA9",
    category: "music",
  },
  {
    key: "lastfm",
    label: "Last.fm",
    baseUrl: "https://www.last.fm/user/{}",
    color: "#D51007",
    category: "music",
  },
  {
    key: "spotify_profile",
    label: "Spotify",
    baseUrl: "https://open.spotify.com/user/{}",
    color: "#1DB954",
    category: "music",
  },

  // ── Writing & Blogs ───────────────────────────────────────────────────
  {
    key: "medium",
    label: "Medium",
    baseUrl: "https://medium.com/@{}",
    color: "#000000",
    category: "writing",
  },
  {
    key: "substack",
    label: "Substack",
    baseUrl: "https://{}.substack.com",
    color: "#FF6719",
    category: "writing",
  },
  {
    key: "devto",
    label: "DEV.to",
    baseUrl: "https://dev.to/{}",
    color: "#0A0A0A",
    category: "writing",
  },
  {
    key: "letterboxd",
    label: "Letterboxd",
    baseUrl: "https://letterboxd.com/{}",
    color: "#00E054",
    category: "writing",
  },
  {
    key: "goodreads",
    label: "Goodreads",
    baseUrl: "https://www.goodreads.com/{}",
    color: "#372213",
    category: "writing",
  },

  // ── Support Me ────────────────────────────────────────────────────────
  {
    key: "patreon",
    label: "Patreon",
    baseUrl: "https://www.patreon.com/{}",
    color: "#FF424D",
    category: "support",
  },
  {
    key: "kofi",
    label: "Ko-fi",
    baseUrl: "https://ko-fi.com/{}",
    color: "#FF5E5B",
    category: "support",
  },
  {
    key: "buymeacoffee",
    label: "Buy Me a Coffee",
    baseUrl: "https://www.buymeacoffee.com/{}",
    color: "#FFDD00",
    category: "support",
  },
  {
    key: "cashapp",
    label: "Cash App",
    baseUrl: "https://cash.app/$",
    color: "#00D632",
    category: "support",
  },
  {
    key: "venmo",
    label: "Venmo",
    baseUrl: "https://venmo.com/{}",
    color: "#3D95CE",
    category: "support",
  },
  {
    key: "paypal",
    label: "PayPal",
    baseUrl: "https://paypal.me/{}",
    color: "#003087",
    category: "support",
  },

  // ── Professional ──────────────────────────────────────────────────────
  {
    key: "github",
    label: "GitHub",
    baseUrl: "https://github.com/{}",
    color: "#181717",
    category: "professional",
  },
  {
    key: "linkedin",
    label: "LinkedIn",
    baseUrl: "https://linkedin.com/in/{}",
    color: "#0A66C2",
    category: "professional",
  },
  {
    key: "fiverr",
    label: "Fiverr",
    baseUrl: "https://www.fiverr.com/{}",
    color: "#1DBF73",
    category: "professional",
  },

  // ── Other ─────────────────────────────────────────────────────────────
  {
    key: "website",
    label: "Website",
    baseUrl: "{}",
    color: "#6E6E6E",
    category: "other",
  },
  {
    key: "email",
    label: "Email",
    baseUrl: "mailto:{}",
    color: "#6E6E6E",
    category: "other",
  },
  {
    key: "onlyfans",
    label: "OnlyFans",
    baseUrl: "https://onlyfans.com/{}",
    color: "#008CCF",
    category: "other",
  },
];

// ── Lookup Maps ──────────────────────────────────────────────────────────

/** Service key → SocialService lookup. */
export const SERVICES_BY_KEY: Record<string, SocialService> = {};
for (const s of ALL_SERVICES) {
  SERVICES_BY_KEY[s.key] = s;
}

/** Services grouped by category for the settings UI. */
export const SERVICES_BY_CATEGORY: Record<
  SocialCategory,
  SocialService[]
> = {} as Record<SocialCategory, SocialService[]>;
for (const s of ALL_SERVICES) {
  if (!SERVICES_BY_CATEGORY[s.category]) {
    SERVICES_BY_CATEGORY[s.category] = [];
  }
  SERVICES_BY_CATEGORY[s.category].push(s);
}
