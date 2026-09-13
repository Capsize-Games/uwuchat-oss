import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useEventBus } from "@/features/events/useEventBus";
import styles from "./PanelWeatherTab.module.css";
import {
  fetchWeather,
  type WeatherData,
  type ForecastDay,
} from "../../../api/user";
import { useAuth } from "../../../hooks/useAuth";
import { useIsMobile } from "../../../hooks/useIsMobile";

// WMO weather interpretation codes → emoji
// https://www.nodc.noaa.gov/archive/arc0021/0002199/1.1/data/0-data/HTML/WMO-CODE/WMO4677.HTM
function weatherIcon(code: number, isDay: number): string {
  const night = isDay === 0;
  if (code === 0) return night ? "🌙" : "☀️";
  if (code <= 3) return night ? "🌙" : "🌤️";
  if (code <= 19) return "☁️";
  if (code <= 29) return "🌫️";
  if (code <= 39) return "🌧️";
  if (code <= 49) return "🌫️";
  if (code <= 59) return "🌦️";
  if (code <= 69) return "🌧️";
  if (code <= 79) return "🌨️";
  if (code <= 82) return "🌧️";
  if (code <= 86) return "🌨️";
  if (code <= 99) return "⛈️";
  return "🌡️";
}

function weatherLabel(code: number, t: (k: string) => string): string {
  if (code === 0) return t("user.weather.label_clear");
  if (code <= 3) return t("user.weather.label_partly_cloudy");
  if (code <= 19) return t("user.weather.label_overcast");
  if (code <= 29) return t("user.weather.label_haze");
  if (code <= 39) return t("user.weather.label_dust");
  if (code <= 49) return t("user.weather.label_fog");
  if (code <= 59) return t("user.weather.label_drizzle");
  if (code <= 69) return t("user.weather.rain");
  if (code <= 79) return t("user.weather.snow");
  if (code <= 82) return t("user.weather.label_showers");
  if (code <= 86) return t("user.weather.label_snow_showers");
  if (code <= 99) return t("user.weather.label_thunderstorm");
  return t("user.weather.label_unknown");
}

/**
 * PanelWeatherTab — current weather + 10-day forecast for the profile panel.
 *
 * Displays a countdown to the next server-side cache expiration and
 * auto-refetches via setTimeout when the TTL elapses.  Also listens for
 * ``weather_data`` push events from the server so that weather updates
 * immediately when any tab triggers a fresh fetch.
 */
const _LS_KEY = "uwuchat:weather_cache";

interface CachedWeather {
  cached_at: string;
  cache_ttl: number;
  data: WeatherData;
}

function _readCachedWeather(): CachedWeather | null {
  try {
    const raw = localStorage.getItem(_LS_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CachedWeather;
    if (!parsed?.cached_at || !parsed?.cache_ttl || !parsed?.data) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function _writeCachedWeather(w: WeatherData): void {
  try {
    localStorage.setItem(_LS_KEY, JSON.stringify({
      cached_at: w.cached_at,
      cache_ttl: w.cache_ttl,
      data: w,
    }));
  } catch { /* quota exceeded — non-critical */ }
}

function _isCacheFresh(cached: CachedWeather): boolean {
  return (
    Date.now() - new Date(cached.cached_at).getTime()
    < cached.cache_ttl * 1000
  );
}

export default function PanelWeatherTab() {
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const isMobile = useIsMobile();
  const [weather, setWeather] = useState<WeatherData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(new Date());
  const [expiresAt, setExpiresAt] = useState<number>(0);
  const fetchingRef = useRef(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Track whether we've already hydrated from localStorage so we
  // don't overwrite fresh websocket data with a stale initial read.
  const hydratedRef = useRef(false);

  // Update clock every 30s
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(id);
  }, []);

  // Listen for server-pushed weather_data events so any open tab
  // updates immediately when a fresh fetch occurs server-side.
  // Also persist to localStorage so the data survives tab switches.
  useEventBus(["weather_data"], (_event, raw) => {
    const payload = raw as { account_id?: number; weather?: WeatherData };
    if (payload?.account_id !== user?.id) return;
    if (payload?.weather) {
      setWeather(payload.weather);
      setExpiresAt(
        new Date(payload.weather.cached_at).getTime()
        + payload.weather.cache_ttl * 1000,
      );
      _writeCachedWeather(payload.weather);
      hydratedRef.current = true;
    }
  });

  const dateLabel = useMemo(() => now.toLocaleDateString(i18n.language, {
    weekday: "short",
    month: "short",
    day: "numeric",
  }), [now, i18n.language]);

  // Human-readable "last refreshed" timestamp from the server's cached_at.
  const lastRefreshedLabel = useMemo(() => {
    if (!weather?.cached_at) return "";
    const dt = new Date(weather.cached_at);
    return dt.toLocaleTimeString(i18n.language, {
      hour: "2-digit",
      minute: "2-digit",
    });
  }, [weather?.cached_at, i18n.language]);

  const fetchData = useCallback(async () => {
    if (fetchingRef.current) return;
    fetchingRef.current = true;
    setLoading(true);
    setError(null);
    try {
      const data = await fetchWeather();
      setWeather(data);
      setExpiresAt(
        new Date(data.cached_at).getTime() + data.cache_ttl * 1000,
      );
      _writeCachedWeather(data);
      hydratedRef.current = true;
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Weather unavailable",
      );
    } finally {
      setLoading(false);
      fetchingRef.current = false;
    }
  }, []);

  // On mount, check localStorage first.  If a fresh cache entry
  // exists use it immediately without a network request.  Otherwise
  // fetch from the server (whose in-memory cache will short-circuit
  // if the data is still fresh).
  useEffect(() => {
    const cached = _readCachedWeather();
    if (cached && _isCacheFresh(cached)) {
      setWeather(cached.data);
      setExpiresAt(
        new Date(cached.cached_at).getTime()
        + cached.cache_ttl * 1000,
      );
      setLoading(false);
      hydratedRef.current = true;
      return;
    }
    fetchData();
  }, [fetchData]);

  // Refetch immediately when the user changes their unit system in
  // Settings — the server has no reason to push a weather_data event
  // just because a preference changed, so without this the panel would
  // keep showing stale-unit data until the page is reloaded.
  useEffect(() => {
    window.addEventListener("uwuchat:unit-system-changed", fetchData);
    return () => {
      window.removeEventListener("uwuchat:unit-system-changed", fetchData);
    };
  }, [fetchData]);

  // Auto-refresh via setTimeout when cache expires.
  // This is more reliable than watching the countdown hit zero because
  // setTimeout is precise and doesn't depend on React render cycles.
  useEffect(() => {
    if (!expiresAt || fetchingRef.current) return;

    const delay = Math.max(1_000, expiresAt - Date.now());
    timerRef.current = setTimeout(() => {
      fetchData();
    }, delay);

    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [expiresAt, fetchData]);

  if (loading) {
    return (
      <div className={styles.center}>
        {t("common.loading")}
      </div>
    );
  }

  if (error || !weather) {
    return (
      <div className={styles.center}>
        {"🌤 "}
        {error || t("user.profile_panel.weather_unavailable")}
      </div>
    );
  }

  const tu = weather.temperature_unit;
  const wu = weather.wind_speed_unit;
  const pu = weather.precipitation_unit;
  const icon = weatherIcon(weather.weather_code, weather.is_day);
  const label = weatherLabel(weather.weather_code, t);

  return (
    <div className={styles.content}>
      {/* Hero — date/updated caption lives inside the card instead of
          floating above it, so it reads as one grouped unit. */}
      <div className={isMobile ? styles.cardSm : styles.card}>
        <div className={styles.metaRow}>
          <span>{dateLabel}</span>
          <span>
            {t("user.weather.updated_at", { time: lastRefreshedLabel })}
          </span>
        </div>
        <div className={styles.heroRow}>
          <span className={styles.heroIcon}>{icon}</span>
          <div className={styles.heroInfo}>
            <div className={styles.heroTemp}>
              {weather.temperature}{tu}
            </div>
            <div className={styles.heroLabel}>
              {label}
              {weather.is_day === 0 ? t("user.weather.night") : ""}
            </div>
          </div>
          <div className={styles.heroAside}>
            <span>
              {t("user.weather.feels_like")} {weather.apparent_temperature}{tu}
            </span>
            <span>{t("user.weather.humidity")} {weather.humidity}%</span>
          </div>
        </div>
      </div>

      {/* Detail grid */}
      <div className={isMobile ? `${styles.cardSm} ${styles.cardMt}` : `${styles.card} ${styles.cardMt}`}>
        <div className={styles.grid}>
          <span>{t("user.weather.cloud_cover")}</span>
          <span className={styles.gridValue}>{weather.cloud_cover}%</span>

          {weather.is_day === 1 && (
            <>
              <span>{t("user.weather.uv_index")}</span>
              <span className={styles.gridValue}>
                {weather.uv_index}{" "}
                <span
                  className={styles.uvBadge}
                  // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
                  style={{
                    "--uv-bg": _uvBadgeBg(weather.uv_index),
                    "--uv-color": _uvBadgeColor(weather.uv_index),
                  } as React.CSSProperties}
                >
                  {_uvLabel(weather.uv_index, t)}
                </span>
              </span>
            </>
          )}

          <span>{t("user.weather.wind")}</span>
          <span className={styles.gridValue}>
            {weather.wind_speed} {wu} {_windDir(weather.wind_direction)}
          </span>

          <span>{t("user.weather.gusts")}</span>
          <span className={styles.gridValue}>{weather.wind_gusts} {wu}</span>

          {weather.precipitation > 0 && (
            <>
              <span>{t("user.weather.precip")}</span>
              <span className={styles.gridValue}>{weather.precipitation} {pu}</span>
            </>
          )}
          {weather.rain > 0 && (
            <>
              <span>{t("user.weather.rain")}</span>
              <span className={styles.gridValue}>{weather.rain} {pu}</span>
            </>
          )}
          {weather.snowfall > 0 && (
            <>
              <span>{t("user.weather.snow")}</span>
              <span className={styles.gridValue}>{weather.snowfall} {pu}</span>
            </>
          )}
        </div>
      </div>

      {/* 10-day forecast */}
      {weather.forecast && weather.forecast.length > 0 && (
        <ForecastSection forecast={weather.forecast} t={t} />
      )}
    </div>
  );
}

/* ── Forecast section ───────────────────────────────────── */

const WEEKDAYS_EN = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function ForecastSection({
  forecast,
  t,
}: {
  forecast: ForecastDay[];
  t: (k: string) => string;
}) {
  const weekdays: string[] = t("user.weather.weekdays", {
    returnObjects: true,
  }) as unknown as string[];
  return (
    <div className={styles.forecastSection}>
      <div className={styles.forecastLabel}>
        {t("user.weather.forecast")}
      </div>
      <ForecastHeaderRow t={t} />
      {forecast.map((day, i) => (
        <ForecastRow
          key={day.date}
          day={day}
          index={i}
          weekdays={weekdays}
          t={t}
        />
      ))}
    </div>
  );
}

function ForecastHeaderRow({
  t,
}: {
  t: (k: string) => string;
}) {
  return (
    <div className={styles.forecastHeader}>
      <span className={styles.fcDay}>
        {t("user.weather.forecast_day")}
      </span>
      <span className={styles.fcIcon} />
      <span className={styles.fcCondition}>
        {t("user.weather.forecast_condition")}
      </span>
      <span className={styles.fcHiLo}>
        {t("user.weather.forecast_hi_lo")}
      </span>
      <span className={styles.fcRain}>
        {t("user.weather.forecast_rain")}
      </span>
    </div>
  );
}

function ForecastRow({
  day,
  index,
  weekdays,
  t,
}: {
  day: ForecastDay;
  index: number;
  weekdays: string[];
  t: (k: string) => string;
}) {
  const date = new Date(day.date + "T12:00:00");
  const dayName = index === 0
    ? t("user.weather.today")
    : (weekdays[date.getUTCDay()] ?? WEEKDAYS_EN[date.getUTCDay()]);
  const icon = forecastIcon(day.weather_code);

  const rowClass = index === 0
    ? styles.forecastRowFirst
    : styles.forecastRowBordered;

  return (
    <div className={rowClass}>
      <span className={styles.forecastDay}>
        {dayName}
      </span>
      <span className={styles.forecastIcon}>
        {icon}
      </span>
      <span className={styles.forecastCondition}>
        {weatherLabel(day.weather_code, t)}
      </span>
      <span className={styles.forecastTemps}>
        {day.temperature_max != null && (
          <span className={styles.tempHigh}>
            {Math.round(day.temperature_max)}°
          </span>
        )}
        {day.temperature_min != null && (
          <span className={styles.tempLow}>
            {Math.round(day.temperature_min)}°
          </span>
        )}
      </span>
      {day.precipitation_probability != null &&
        day.precipitation_probability > 0 && (
          <span
            className={
              day.precipitation_probability >= 50
                ? `${styles.forecastPrecip} ${styles.precipHigh}`
                : `${styles.forecastPrecip} ${styles.precipNormal}`
            }
          >
            {day.precipitation_probability}%
          </span>
        )}
    </div>
  );
}

function forecastIcon(code: number): string {
  if (code === 0) return "☀️";
  if (code <= 2) return "⛅";
  if (code === 3) return "☁️";
  if (code >= 45 && code <= 48) return "🌫️";
  if (code >= 51 && code <= 57) return "🌦️";
  if (code >= 61 && code <= 67) return "🌧️";
  if (code >= 71 && code <= 77) return "🌨️";
  if (code >= 80 && code <= 82) return "🌦️";
  if (code >= 85 && code <= 86) return "🌨️";
  if (code >= 95) return "⛈️";
  return "🌤️";
}

// ── helpers ──────────────────────────────────────────────────────

function _uvBadgeBg(index: number): string {
  if (index >= 8) return "rgba(168,85,247,0.2)";
  if (index >= 6) return "rgba(234,88,12,0.2)";
  if (index >= 3) return "rgba(234,179,8,0.2)";
  return "rgba(34,197,94,0.15)";
}

function _uvBadgeColor(index: number): string {
  if (index >= 8) return "#a855f7";
  if (index >= 6) return "#ea580c";
  if (index >= 3) return "#eab308";
  return "#22c55e";
}

function _uvLabel(index: number, t: (k: string) => string): string {
  if (index >= 11) return t("user.weather.uv_extreme");
  if (index >= 8) return t("user.weather.uv_very_high");
  if (index >= 6) return t("user.weather.uv_high");
  if (index >= 3) return t("user.weather.uv_moderate");
  return t("user.weather.uv_low");
}

function _windDir(deg: number): string {
  const dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
  return dirs[Math.round(deg / 22.5) % 16] || "";
}
