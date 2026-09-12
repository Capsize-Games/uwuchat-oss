/** Curated real-world cities for chatbot home-base assignment.
 *
 * Each entry covers one complete location with timezone, locale, coordinates,
 * and a natural-language home_description injected into the system prompt.
 * Lat/lng are reserved for future travel-distance features.
 */
export interface LocationEntry {
  timezone: string;
  locale: string;
  city: string;
  region: string;
  country_code: string;
  latitude: number;
  longitude: number;
  home_description: string;
}

const LOCATIONS: LocationEntry[] = [
  // ---- North America ----
  {
    timezone: "America/New_York",
    locale: "en-US",
    city: "New York City",
    region: "New York",
    country_code: "US",
    latitude: 40.7128,
    longitude: -74.006,
    home_description:
      "lives in a cozy apartment in the East Village, New York City",
  },
  {
    timezone: "America/Chicago",
    locale: "en-US",
    city: "Chicago",
    region: "Illinois",
    country_code: "US",
    latitude: 41.8781,
    longitude: -87.6298,
    home_description:
      "rents a loft in Wicker Park, Chicago",
  },
  {
    timezone: "America/Denver",
    locale: "en-US",
    city: "Denver",
    region: "Colorado",
    country_code: "US",
    latitude: 39.7392,
    longitude: -104.9903,
    home_description:
      "shares a house near City Park, Denver with a view of the mountains",
  },
  {
    timezone: "America/Los_Angeles",
    locale: "en-US",
    city: "Los Angeles",
    region: "California",
    country_code: "US",
    latitude: 34.0522,
    longitude: -118.2437,
    home_description:
      "lives in a sunny apartment in Echo Park, Los Angeles",
  },
  {
    timezone: "America/Los_Angeles",
    locale: "en-US",
    city: "San Francisco",
    region: "California",
    country_code: "US",
    latitude: 37.7749,
    longitude: -122.4194,
    home_description:
      "rents a tiny studio in the Mission District, San Francisco",
  },
  {
    timezone: "America/Vancouver",
    locale: "en-CA",
    city: "Vancouver",
    region: "British Columbia",
    country_code: "CA",
    latitude: 49.2827,
    longitude: -123.1207,
    home_description:
      "lives in a high-rise condo in downtown Vancouver near the seawall",
  },
  {
    timezone: "America/Toronto",
    locale: "en-CA",
    city: "Toronto",
    region: "Ontario",
    country_code: "CA",
    latitude: 43.6532,
    longitude: -79.3832,
    home_description:
      "stays in a converted loft on Queen Street West, Toronto",
  },
  {
    timezone: "America/Mexico_City",
    locale: "es-MX",
    city: "Mexico City",
    region: "CDMX",
    country_code: "MX",
    latitude: 19.4326,
    longitude: -99.1332,
    home_description:
      "lives in a colorful apartment in Roma Norte, Mexico City",
  },
  {
    timezone: "America/Chicago",
    locale: "en-US",
    city: "Austin",
    region: "Texas",
    country_code: "US",
    latitude: 30.2672,
    longitude: -97.7431,
    home_description:
      "shares a quirky house in East Austin near the food trucks",
  },
  {
    timezone: "America/New_York",
    locale: "en-US",
    city: "Atlanta",
    region: "Georgia",
    country_code: "US",
    latitude: 33.749,
    longitude: -84.388,
    home_description:
      "lives in a craftsman bungalow in the Virginia-Highland neighborhood, Atlanta",
  },
  {
    timezone: "America/Anchorage",
    locale: "en-US",
    city: "Anchorage",
    region: "Alaska",
    country_code: "US",
    latitude: 61.2181,
    longitude: -149.9003,
    home_description:
      "lives in a cabin on the outskirts of Anchorage with mountain views",
  },
  {
    timezone: "Pacific/Honolulu",
    locale: "en-US",
    city: "Honolulu",
    region: "Hawaii",
    country_code: "US",
    latitude: 21.3069,
    longitude: -157.8583,
    home_description:
      "rents a small apartment in Waikiki, Honolulu just blocks from the beach",
  },

  // ---- South America ----
  {
    timezone: "America/Sao_Paulo",
    locale: "pt-BR",
    city: "São Paulo",
    region: "São Paulo",
    country_code: "BR",
    latitude: -23.5505,
    longitude: -46.6333,
    home_description:
      "lives in a modern apartment in Vila Madalena, São Paulo",
  },
  {
    timezone: "America/Argentina/Buenos_Aires",
    locale: "es-AR",
    city: "Buenos Aires",
    region: "Buenos Aires",
    country_code: "AR",
    latitude: -34.6037,
    longitude: -58.3816,
    home_description:
      "rents a flat in Palermo Soho, Buenos Aires with a rooftop terrace",
  },
  {
    timezone: "America/Bogota",
    locale: "es-CO",
    city: "Bogotá",
    region: "Bogotá",
    country_code: "CO",
    latitude: 4.711,
    longitude: -74.0721,
    home_description:
      "lives in a hillside apartment in La Candelaria, Bogotá",
  },
  {
    timezone: "America/Lima",
    locale: "es-PE",
    city: "Lima",
    region: "Lima",
    country_code: "PE",
    latitude: -12.0464,
    longitude: -77.0428,
    home_description:
      "stays in a breezy apartment in Miraflores, Lima overlooking the coast",
  },
  {
    timezone: "America/Santiago",
    locale: "es-CL",
    city: "Santiago",
    region: "Santiago",
    country_code: "CL",
    latitude: -33.4489,
    longitude: -70.6693,
    home_description:
      "lives in a sleek apartment in Providencia, Santiago with Andean views",
  },

  // ---- Europe ----
  {
    timezone: "Europe/London",
    locale: "en-GB",
    city: "London",
    region: "England",
    country_code: "GB",
    latitude: 51.5074,
    longitude: -0.1278,
    home_description:
      "rents a small flat near Camden Market, London",
  },
  {
    timezone: "Europe/Paris",
    locale: "fr-FR",
    city: "Paris",
    region: "Île-de-France",
    country_code: "FR",
    latitude: 48.8566,
    longitude: 2.3522,
    home_description:
      "lives in a charming attic studio in Montmartre, Paris",
  },
  {
    timezone: "Europe/Berlin",
    locale: "de-DE",
    city: "Berlin",
    region: "Berlin",
    country_code: "DE",
    latitude: 52.52,
    longitude: 13.405,
    home_description:
      "shares an altbau apartment in Kreuzberg, Berlin full of plants",
  },
  {
    timezone: "Europe/Madrid",
    locale: "es-ES",
    city: "Madrid",
    region: "Madrid",
    country_code: "ES",
    latitude: 40.4168,
    longitude: -3.7038,
    home_description:
      "lives in a lively apartment in Malasaña, Madrid near the plazas",
  },
  {
    timezone: "Europe/Rome",
    locale: "it-IT",
    city: "Rome",
    region: "Lazio",
    country_code: "IT",
    latitude: 41.9028,
    longitude: 12.4964,
    home_description:
      "rents a small apartment in Trastevere, Rome with a courtyard",
  },
  {
    timezone: "Europe/Amsterdam",
    locale: "nl-NL",
    city: "Amsterdam",
    region: "North Holland",
    country_code: "NL",
    latitude: 52.3676,
    longitude: 4.9041,
    home_description:
      "lives in a canal-side apartment in De Pijp, Amsterdam",
  },
  {
    timezone: "Europe/Stockholm",
    locale: "sv-SE",
    city: "Stockholm",
    region: "Stockholm",
    country_code: "SE",
    latitude: 59.3293,
    longitude: 18.0686,
    home_description:
      "stays in a minimalist apartment on Södermalm, Stockholm",
  },
  {
    timezone: "Europe/Prague",
    locale: "cs-CZ",
    city: "Prague",
    region: "Prague",
    country_code: "CZ",
    latitude: 50.0755,
    longitude: 14.4378,
    home_description:
      "lives in a cozy flat in Vinohrady, Prague with high ceilings",
  },
  {
    timezone: "Europe/Istanbul",
    locale: "tr-TR",
    city: "Istanbul",
    region: "Istanbul",
    country_code: "TR",
    latitude: 41.0082,
    longitude: 28.9784,
    home_description:
      "rents an apartment in Kadıköy, Istanbul with rooftop views of the Bosphorus",
  },
  {
    timezone: "Europe/Athens",
    locale: "el-GR",
    city: "Athens",
    region: "Attica",
    country_code: "GR",
    latitude: 37.9838,
    longitude: 23.7275,
    home_description:
      "lives in a sunny apartment in Exarcheia, Athens near the hills",
  },
  {
    timezone: "Europe/Moscow",
    locale: "ru-RU",
    city: "Moscow",
    region: "Moscow",
    country_code: "RU",
    latitude: 55.7558,
    longitude: 37.6173,
    home_description:
      "stays in a high-rise apartment near Tverskaya Street, Moscow",
  },
  {
    timezone: "Europe/Warsaw",
    locale: "pl-PL",
    city: "Warsaw",
    region: "Masovia",
    country_code: "PL",
    latitude: 52.2297,
    longitude: 21.0122,
    home_description:
      "lives in a renovated apartment in Praga district, Warsaw",
  },
  {
    timezone: "Europe/Lisbon",
    locale: "pt-PT",
    city: "Lisbon",
    region: "Lisbon",
    country_code: "PT",
    latitude: 38.7223,
    longitude: -9.1393,
    home_description:
      "rents a tiled apartment in Alfama, Lisbon with fado music drifting up from the street",
  },

  // ---- Africa ----
  {
    timezone: "Africa/Lagos",
    locale: "en-NG",
    city: "Lagos",
    region: "Lagos",
    country_code: "NG",
    latitude: 6.5244,
    longitude: 3.3792,
    home_description:
      "lives in a vibrant apartment on Lagos Island with Lagos Lagoon views",
  },
  {
    timezone: "Africa/Nairobi",
    locale: "en-KE",
    city: "Nairobi",
    region: "Nairobi",
    country_code: "KE",
    latitude: -1.2921,
    longitude: 36.8219,
    home_description:
      "rents an apartment in Kilimani, Nairobi near the acacia-lined streets",
  },
  {
    timezone: "Africa/Johannesburg",
    locale: "en-ZA",
    city: "Johannesburg",
    region: "Gauteng",
    country_code: "ZA",
    latitude: -26.2041,
    longitude: 28.0473,
    home_description:
      "lives in a modern loft in Maboneng Precinct, Johannesburg",
  },
  {
    timezone: "Africa/Cairo",
    locale: "ar-EG",
    city: "Cairo",
    region: "Cairo",
    country_code: "EG",
    latitude: 30.0444,
    longitude: 31.2357,
    home_description:
      "stays in an apartment in Zamalek, Cairo with Nile river views",
  },
  {
    timezone: "Africa/Casablanca",
    locale: "ar-MA",
    city: "Casablanca",
    region: "Casablanca-Settat",
    country_code: "MA",
    latitude: 33.5731,
    longitude: -7.5898,
    home_description:
      "lives in an art deco apartment in the city center, Casablanca",
  },
  {
    timezone: "Africa/Addis_Ababa",
    locale: "am-ET",
    city: "Addis Ababa",
    region: "Addis Ababa",
    country_code: "ET",
    latitude: 9.032,
    longitude: 38.7469,
    home_description:
      "rents a hillside apartment in Bole, Addis Ababa with eucalyptus views",
  },

  // ---- Middle East ----
  {
    timezone: "Asia/Dubai",
    locale: "ar-AE",
    city: "Dubai",
    region: "Dubai",
    country_code: "AE",
    latitude: 25.2048,
    longitude: 55.2708,
    home_description:
      "lives in a high-rise apartment in Dubai Marina with skyline views",
  },
  {
    timezone: "Asia/Jerusalem",
    locale: "he-IL",
    city: "Jerusalem",
    region: "Jerusalem",
    country_code: "IL",
    latitude: 31.7683,
    longitude: 35.2137,
    home_description:
      "stays in a stone-walled apartment in Nachlaot, Jerusalem",
  },
  {
    timezone: "Asia/Tehran",
    locale: "fa-IR",
    city: "Tehran",
    region: "Tehran",
    country_code: "IR",
    latitude: 35.6892,
    longitude: 51.389,
    home_description:
      "lives in an apartment in northern Tehran with mountain views",
  },
  {
    timezone: "Asia/Riyadh",
    locale: "ar-SA",
    city: "Riyadh",
    region: "Riyadh",
    country_code: "SA",
    latitude: 24.7136,
    longitude: 46.6753,
    home_description:
      "rents a modern apartment in the diplomatic quarter, Riyadh",
  },

  // ---- South Asia ----
  {
    timezone: "Asia/Kolkata",
    locale: "en-IN",
    city: "Mumbai",
    region: "Maharashtra",
    country_code: "IN",
    latitude: 19.076,
    longitude: 72.8777,
    home_description:
      "lives in a compact apartment in Bandra West, Mumbai near the sea",
  },
  {
    timezone: "Asia/Kolkata",
    locale: "hi-IN",
    city: "Delhi",
    region: "Delhi",
    country_code: "IN",
    latitude: 28.7041,
    longitude: 77.1025,
    home_description:
      "stays in a flat in Hauz Khas Village, Delhi surrounded by ruins and galleries",
  },
  {
    timezone: "Asia/Kolkata",
    locale: "en-IN",
    city: "Bangalore",
    region: "Karnataka",
    country_code: "IN",
    latitude: 12.9716,
    longitude: 77.5946,
    home_description:
      "rents an apartment in Indiranagar, Bangalore near the startup cafés",
  },
  {
    timezone: "Asia/Karachi",
    locale: "ur-PK",
    city: "Karachi",
    region: "Sindh",
    country_code: "PK",
    latitude: 24.8607,
    longitude: 67.0011,
    home_description:
      "lives in a flat in Clifton, Karachi with sea breezes from the Arabian Sea",
  },
  {
    timezone: "Asia/Dhaka",
    locale: "bn-BD",
    city: "Dhaka",
    region: "Dhaka",
    country_code: "BD",
    latitude: 23.8103,
    longitude: 90.4125,
    home_description:
      "stays in an apartment in Gulshan, Dhaka near the lake",
  },
  {
    timezone: "Asia/Colombo",
    locale: "si-LK",
    city: "Colombo",
    region: "Western Province",
    country_code: "LK",
    latitude: 6.9271,
    longitude: 79.8612,
    home_description:
      "lives in a flat near Galle Face Green, Colombo with ocean views",
  },

  // ---- Southeast Asia ----
  {
    timezone: "Asia/Bangkok",
    locale: "th-TH",
    city: "Bangkok",
    region: "Bangkok",
    country_code: "TH",
    latitude: 13.7563,
    longitude: 100.5018,
    home_description:
      "rents a condo in Thonglor, Bangkok near the night markets",
  },
  {
    timezone: "Asia/Jakarta",
    locale: "id-ID",
    city: "Jakarta",
    region: "Jakarta",
    country_code: "ID",
    latitude: -6.2088,
    longitude: 106.8456,
    home_description:
      "lives in an apartment in Kemang, South Jakarta with a rooftop garden",
  },
  {
    timezone: "Asia/Manila",
    locale: "en-PH",
    city: "Manila",
    region: "Metro Manila",
    country_code: "PH",
    latitude: 14.5995,
    longitude: 120.9842,
    home_description:
      "stays in a condo in Makati, Manila overlooking the skyline",
  },
  {
    timezone: "Asia/Singapore",
    locale: "en-SG",
    city: "Singapore",
    region: "Singapore",
    country_code: "SG",
    latitude: 1.3521,
    longitude: 103.8198,
    home_description:
      "lives in a modern HDB flat in Tiong Bahru, Singapore",
  },
  {
    timezone: "Asia/Ho_Chi_Minh",
    locale: "vi-VN",
    city: "Ho Chi Minh City",
    region: "Ho Chi Minh City",
    country_code: "VN",
    latitude: 10.8231,
    longitude: 106.6297,
    home_description:
      "rents a narrow apartment in District 1, Ho Chi Minh City above a café",
  },
  {
    timezone: "Asia/Kuala_Lumpur",
    locale: "ms-MY",
    city: "Kuala Lumpur",
    region: "Kuala Lumpur",
    country_code: "MY",
    latitude: 3.139,
    longitude: 101.6869,
    home_description:
      "lives in a condo in Bangsar, Kuala Lumpur with Petronas Towers views",
  },

  // ---- East Asia ----
  {
    timezone: "Asia/Tokyo",
    locale: "ja-JP",
    city: "Tokyo",
    region: "Tokyo",
    country_code: "JP",
    latitude: 35.6762,
    longitude: 139.6503,
    home_description:
      "lives in a compact apartment in Shimokitazawa, Tokyo near the vintage shops",
  },
  {
    timezone: "Asia/Seoul",
    locale: "ko-KR",
    city: "Seoul",
    region: "Seoul",
    country_code: "KR",
    latitude: 37.5665,
    longitude: 126.978,
    home_description:
      "stays in a small apartment in Hongdae, Seoul filled with art supplies",
  },
  {
    timezone: "Asia/Shanghai",
    locale: "zh-CN",
    city: "Shanghai",
    region: "Shanghai",
    country_code: "CN",
    latitude: 31.2304,
    longitude: 121.4737,
    home_description:
      "rents a lane-house apartment in the Former French Concession, Shanghai",
  },
  {
    timezone: "Asia/Hong_Kong",
    locale: "zh-HK",
    city: "Hong Kong",
    region: "Hong Kong",
    country_code: "HK",
    latitude: 22.3193,
    longitude: 114.1694,
    home_description:
      "lives in a high-rise flat in Mong Kok, Hong Kong above the neon streets",
  },
  {
    timezone: "Asia/Taipei",
    locale: "zh-TW",
    city: "Taipei",
    region: "Taipei",
    country_code: "TW",
    latitude: 25.033,
    longitude: 121.5654,
    home_description:
      "stays in an apartment in Da'an, Taipei near the night markets",
  },
  {
    timezone: "Asia/Beijing",
    locale: "zh-CN",
    city: "Beijing",
    region: "Beijing",
    country_code: "CN",
    latitude: 39.9042,
    longitude: 116.4074,
    home_description:
      "lives in a hutong courtyard apartment in Dongcheng, Beijing",
  },

  // ---- Oceania ----
  {
    timezone: "Australia/Sydney",
    locale: "en-AU",
    city: "Sydney",
    region: "New South Wales",
    country_code: "AU",
    latitude: -33.8688,
    longitude: 151.2093,
    home_description:
      "shares a beachside flat in Bondi, Sydney with surfboards by the door",
  },
  {
    timezone: "Australia/Perth",
    locale: "en-AU",
    city: "Perth",
    region: "Western Australia",
    country_code: "AU",
    latitude: -31.9505,
    longitude: 115.8605,
    home_description:
      "lives in a sunny townhouse in Fremantle, Perth near the harbour",
  },
  {
    timezone: "Pacific/Auckland",
    locale: "en-NZ",
    city: "Auckland",
    region: "Auckland",
    country_code: "NZ",
    latitude: -36.8485,
    longitude: 174.7633,
    home_description:
      "rents a hillside house in Ponsonby, Auckland with harbour views",
  },

  // ---- Additional cities for coverage ----
  {
    timezone: "America/Vancouver",
    locale: "fr-CA",
    city: "Montreal",
    region: "Quebec",
    country_code: "CA",
    latitude: 45.5017,
    longitude: -73.5673,
    home_description:
      "lives in a walk-up apartment in Le Plateau, Montreal with a spiral staircase",
  },
  {
    timezone: "Europe/Kyiv",
    locale: "uk-UA",
    city: "Kyiv",
    region: "Kyiv",
    country_code: "UA",
    latitude: 50.4501,
    longitude: 30.5234,
    home_description:
      "stays in an apartment in Podil, Kyiv with Dnieper river views",
  },
  {
    timezone: "Europe/Dublin",
    locale: "en-IE",
    city: "Dublin",
    region: "Dublin",
    country_code: "IE",
    latitude: 53.3498,
    longitude: -6.2603,
    home_description:
      "rents a brick terrace house in Ranelagh, Dublin near the canal",
  },
  {
    timezone: "Europe/Oslo",
    locale: "nb-NO",
    city: "Oslo",
    region: "Oslo",
    country_code: "NO",
    latitude: 59.9139,
    longitude: 10.7522,
    home_description:
      "lives in a modern flat in Grünerløkka, Oslo overlooking the river",
  },
];

export default LOCATIONS;
