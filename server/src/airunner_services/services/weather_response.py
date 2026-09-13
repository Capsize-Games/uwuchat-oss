"""Response parsing helpers for Open-Meteo weather API responses.

Separated from ``weather_service.py`` to keep each file under the 250-line
limit.  All functions are ≤20 lines.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

WMO_LABELS: dict[int, str] = {
    0: "Clear", 1: "Mostly clear", 2: "Partly cloudy",
    3: "Overcast", 45: "Foggy", 48: "Rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    56: "Light freezing drizzle", 57: "Dense freezing drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Heavy freezing rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    77: "Snow grains",
    80: "Slight rain showers", 81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def wmo_label(code: int) -> str:
    return WMO_LABELS.get(code, "Unknown")


def _unit_labels(is_metric: bool) -> tuple[str, str, str]:
    if is_metric:
        return ("°C", "km/h", "mm")
    return ("°F", "mph", "inch")


def _current_conditions(c) -> dict:
    """Return current conditions fields (temperature, wind, etc.)."""
    return {
        "temperature": round(c.get("temperature_2m", 0), 1),
        "precipitation": round(c.get("precipitation", 0), 2),
        "rain": round(c.get("rain", 0), 2),
        "showers": round(c.get("showers", 0), 2),
        "snowfall": round(c.get("snowfall", 0), 2),
        "wind_speed": round(c.get("wind_speed_10m", 0), 1),
        "wind_direction": round(c.get("wind_direction_10m", 0), 0),
        "wind_gusts": round(c.get("wind_gusts_10m", 0), 1),
    }


def _current_meta(c, code, t, ws, pr) -> dict:
    """Return current metadata fields (labels, units, timestamps)."""
    return {
        "temperature_unit": t,
        "wind_speed_unit": ws,
        "precipitation_unit": pr,
        "weather_code": code,
        "weather_label": wmo_label(code),
        "humidity": round(c.get("relative_humidity_2m", 0), 0),
        "apparent_temperature": round(
            c.get("apparent_temperature", 0), 1,
        ),
        "cloud_cover": round(c.get("cloud_cover", 0), 0),
        "uv_index": round(c.get("uv_index", 0), 1),
        "is_day": c.get("is_day", 1),
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }


def parse_current(data: dict, is_metric: bool) -> dict[str, Any]:
    c = data.get("current", {})
    code = c.get("weather_code", 0) or 0
    t, ws, pr = _unit_labels(is_metric)
    result = _current_conditions(c)
    result.update(_current_meta(c, code, t, ws, pr))
    return result


def _forecast_line(i, times, codes, t_max, t_min, precip, pop) -> str:
    label = wmo_label(int(codes[i]) if i < len(codes) else 0)
    hi = round(t_max[i], 1) if i < len(t_max) else "?"
    lo = round(t_min[i], 1) if i < len(t_min) else "?"
    pp = int(pop[i]) if i < len(pop) else "?"
    return (
        f"- {times[i]}: {label}, H {hi} / L {lo}, "
        f"precip {round(precip[i], 2)} ({pp}%)"
    )


def _forecast_lines(data: dict, n: int) -> list[str]:
    daily = data.get("daily", {})
    codes = daily.get("weather_code", [])
    t_max = daily.get("temperature_2m_max", [])
    t_min = daily.get("temperature_2m_min", [])
    precip = daily.get("precipitation_sum", [])
    pop = daily.get("precipitation_probability_max", [])
    return [
        _forecast_line(i, daily.get("time", []), codes, t_max,
                       t_min, precip, pop)
        for i in range(n)
    ]


def forecast_text(data: dict) -> str:
    daily = data.get("daily", {})
    times = daily.get("time", [])
    n = min(len(times), 10)
    if n == 0:
        return ""
    return "\n".join(
        ["10-day forecast:"] + _forecast_lines(data, n),
    )


def _safe(a, i, fn, default=None):
    return fn(a[i]) if i < len(a) else default


def _build_day_dict(
    i, dates, codes, t_max, t_min, precip, pop, wind, t, wu,
) -> dict:
    code = int(codes[i]) if i < len(codes) else 0
    return {
        "date": dates[i], "weather_code": code,
        "weather_label": wmo_label(code),
        "temperature_max": _safe(t_max, i, round, None),
        "temperature_min": _safe(t_min, i, round, None),
        "precipitation_sum": _safe(precip, i, round, 0.0),
        "precipitation_probability": _safe(pop, i, int, None),
        "wind_speed_max": _safe(wind, i, round, None),
        "temperature_unit": t, "wind_speed_unit": wu,
    }


def daily_array(data, temp_label, wind_unit) -> list[dict[str, Any]]:
    daily = data.get("daily", {})
    dates = daily.get("time", [])
    return [
        _build_day_dict(
            i, dates,
            daily.get("weather_code", []),
            daily.get("temperature_2m_max", []),
            daily.get("temperature_2m_min", []),
            daily.get("precipitation_sum", []),
            daily.get("precipitation_probability_max", []),
            daily.get("wind_speed_10m_max", []),
            temp_label, wind_unit,
        )
        for i in range(len(dates))
    ]


def _build_hour_dict(
    i, t, times, temps, codes, precip, pop, wind, hum, app, t_l, wu,
) -> dict:
    code = int(codes[i]) if i < len(codes) else 0
    from datetime import datetime as _dt
    return {
        "time": _dt.fromisoformat(t).strftime("%-H:%M"),
        "temperature": _safe(temps, i, lambda v: round(v, 1), 0),
        "weather_code": code, "weather_label": wmo_label(code),
        "apparent_temperature": _safe(app, i,
                                      lambda v: round(v, 1), 0),
        "precipitation": _safe(precip, i,
                               lambda v: round(v, 2), 0.0),
        "precipitation_probability": _safe(pop, i, int, 0),
        "wind_speed": _safe(wind, i, lambda v: round(v, 1), 0),
        "humidity": _safe(hum, i, lambda v: round(v, 0), 0),
        "temperature_unit": t_l, "wind_speed_unit": wu,
    }


def _is_today(t: str) -> bool:
    return t.startswith(datetime.now(timezone.utc).strftime("%Y-%m-%d"))


def hourly_array(data, temp_label, wind_unit) -> list[dict[str, Any]]:
    h = data.get("hourly", {})
    times = h.get("time", [])
    return [
        _build_hour_dict(
            i, t, times,
            h.get("temperature_2m", []),
            h.get("weather_code", []),
            h.get("precipitation", []),
            h.get("precipitation_probability", []),
            h.get("wind_speed_10m", []),
            h.get("relative_humidity_2m", []),
            h.get("apparent_temperature", []),
            temp_label, wind_unit,
        )
        for i, t in enumerate(times) if _is_today(t)
    ]
