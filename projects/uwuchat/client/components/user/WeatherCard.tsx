import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  fetchWeather,
  type WeatherData,
  type ForecastDay,
} from "../../api/user";
import styles from "./WeatherCard.module.css";

export default function WeatherCard() {
  const { t } = useTranslation();
  const [weather, setWeather] = useState<WeatherData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await fetchWeather();
        if (!cancelled) setWeather(data);
      } catch {
        if (!cancelled) setError(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  if (loading) return null;
  if (error || !weather) {
    return (
      <div className={styles.errorCard}>
        {t("user.weather.weather_unavailable_card")}
      </div>
    );
  }

  return (
    <div className={styles.weatherCard}>
      <CurrentConditions weather={weather} t={t} />
      <ForecastList forecast={weather.forecast} t={t} />
    </div>
  );
}

function CurrentConditions({
  weather,
  t,
}: {
  weather: WeatherData;
  t: (k: string) => string;
}) {
  const temp = weather.temperature;
  const tu = weather.temperature_unit;
  const w = weather.wind_speed;
  const wu = weather.wind_speed_unit;
  const g = weather.wind_gusts;
  const precip = weather.precipitation;
  const snow = weather.snowfall;
  const pu = weather.precipitation_unit;
  const label = weatherLabelLocal(weather.weather_code, t);

  const icon = temp >= 80 ? "☀️" : temp >= 60 ? "🌤️" : temp >= 40 ? "🌥️"
    : temp >= 20 ? "❄️" : "🥶";

  return (
    <div className={styles.curCard}>
      <span className={styles.curIcon}>{icon}</span>
      <div className={styles.curInfo}>
        <span className={styles.curTemp}>
          {temp}{tu} · {label} · {t("user.weather.wind")} {w} {wu}
        </span>
        <span className={styles.curDetails}>
          {precip > 0 && <>{t("user.weather.precip")}: {precip} {pu} · </>}
          {snow > 0 && <>{t("user.weather.snow")}: {snow} {pu} · </>}
          {t("user.weather.gusts")} {g} {wu}
        </span>
      </div>
    </div>
  );
}

const WEEKDAYS_EN = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function ForecastList({
  forecast,
  t,
}: {
  forecast: ForecastDay[];
  t: (k: string) => string;
}) {
  if (!forecast || forecast.length === 0) return null;

  const weekdays: string[] = t("user.weather.weekdays", {
    returnObjects: true,
  }) as unknown as string[];

  return (
    <div className={styles.fcCard}>
      <div className={styles.fcHeader}>
        {t("user.weather.forecast")}
      </div>
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
  const icon = weatherIcon(day.weather_code);

  return (
    // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
    <div className={styles.fcRow} style={{ borderTop: index > 0 ? "1px solid rgba(255,255,255,0.05)" : "none" }}>
      <span className={styles.fcDay}>{dayName}</span>
      <span className={styles.fcIcon}>{icon}</span>
      <span className={styles.fcLabel}>{weatherLabelLocal(day.weather_code, t)}</span>
      <span className={styles.fcTemps}>
        {day.temperature_max != null && (
          <span className={styles.fcHi}>{Math.round(day.temperature_max)}°</span>
        )}
        {day.temperature_min != null && (
          <span className={styles.fcLo}>{Math.round(day.temperature_min)}°</span>
        )}
      </span>
      {day.precipitation_probability != null && day.precipitation_probability > 0 && (
        // eslint-disable-next-line no-restricted-syntax -- dynamic value from prop/state/computation
        <span className={styles.fcPrecip} style={{ color: day.precipitation_probability >= 50 ? "#4fc3f7" : "var(--theme-text-secondary)" }}>
          {day.precipitation_probability}%
        </span>
      )}
    </div>
  );
}

function weatherLabelLocal(code: number, t: (k: string) => string): string {
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

function weatherIcon(code: number): string {
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
