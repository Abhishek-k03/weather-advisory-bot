"""Open-Meteo client: geocoding + forecast + snapshot. No LLM in this file.

The snapshot built here is the only source of numbers the bot ever reports.
"""
from datetime import datetime, timedelta

import requests

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = 10  # seconds

# Open-Meteo only returns values for fields listed explicitly in current=/hourly=.
FIELDS = [
    "temperature_2m",
    "apparent_temperature",
    "precipitation",
    "precipitation_probability",
    "wind_speed_10m",
    "wind_gusts_10m",
    "uv_index",
    "pressure_msl",
    "weather_code",
]
# Computed below from the hourly data, never by the model.
DERIVED_FIELDS = ["precipitation_next_24h"]
SNAPSHOT_FIELDS = FIELDS + DERIVED_FIELDS

# field -> (label shown to users, unit suffix)
READINGS = {
    "temperature_2m": ("temperature", "°C"),
    "apparent_temperature": ("feels like", "°C"),
    "precipitation": ("precipitation", " mm"),
    "precipitation_probability": ("chance of rain", "%"),
    "wind_speed_10m": ("wind", " km/h"),
    "wind_gusts_10m": ("gusts", " km/h"),
    "uv_index": ("UV index", ""),
    "pressure_msl": ("pressure", " hPa"),
    "weather_code": ("WMO weather code", ""),
    "precipitation_next_24h": ("rain next 24h", " mm"),
}

# time_window -> (day offset, first local hour, last local hour)
WINDOWS = {
    "morning": (0, 6, 11),
    "afternoon": (0, 12, 16),
    "evening": (0, 17, 20),
    "night": (0, 21, 23),
    "tomorrow": (1, 6, 20),
}


class WeatherUnavailable(Exception):
    """Location could not be resolved or the API could not be reached.

    Both cases raise this one type so they take the same honest-failure path.
    """


def geocode(city: str) -> dict:
    try:
        r = requests.get(GEO_URL, params={"name": city, "count": 1}, timeout=TIMEOUT)
        r.raise_for_status()
        results = r.json().get("results")
    except (requests.RequestException, ValueError) as e:
        raise WeatherUnavailable(f"geocoding failed for {city!r}: {e}") from e
    if not results:
        raise WeatherUnavailable(f"no location found for {city!r}")
    hit = results[0]  # documented default: take the first match
    name = ", ".join(p for p in (hit.get("name"), hit.get("admin1"), hit.get("country")) if p)
    return {"name": name, "latitude": hit["latitude"], "longitude": hit["longitude"]}


def fetch_forecast(latitude: float, longitude: float) -> dict:
    fields = ",".join(FIELDS)
    try:
        r = requests.get(FORECAST_URL, timeout=TIMEOUT, params={
            "latitude": latitude,
            "longitude": longitude,
            "current": fields,
            "hourly": fields,
            "timezone": "auto",
            "forecast_days": 3,
        })
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError) as e:
        raise WeatherUnavailable(f"forecast request failed: {e}") from e
    if "current" not in data or "hourly" not in data:
        raise WeatherUnavailable("forecast response contained no weather values")
    return data


def describe(field: str, value) -> str:
    """Readable form of one reading, e.g. "gusts 62.3 km/h"."""
    label, unit = READINGS.get(field, (field, ""))
    return f"{label} {value}{unit}"


def worst_value(values):
    """The highest value in a window (ignoring missing hours), or None if all are missing."""
    present = [v for v in values if v is not None]
    return max(present) if present else None


def build_snapshot(data: dict, time_window: str = "now") -> dict:
    """Reduce a raw forecast to one set of numbers for the time window being asked about.

    "now" uses the current block. Any other window takes the worst (highest)
    hourly value of each field, so a threshold crossed at any hour counts.
    """
    hourly = data["hourly"]
    hour_times = [datetime.fromisoformat(t) for t in hourly["time"]]
    now = datetime.fromisoformat(data["current"]["time"])

    if time_window in WINDOWS:
        day_offset, first_hour, last_hour = WINDOWS[time_window]
        day = (now + timedelta(days=day_offset)).date()
        in_window = [i for i, t in enumerate(hour_times)
                     if t.date() == day and first_hour <= t.hour <= last_hour]
        if not in_window:
            raise WeatherUnavailable(f"no hourly forecast for {time_window}")

        values = {field: worst_value(hourly[field][i] for i in in_window) for field in FIELDS}
        window_start = hour_times[in_window[0]]
        label = f"{time_window}, {window_start:%H}:00-{hour_times[in_window[-1]]:%H}:59 local, worst hour"
    else:
        values = {field: data["current"].get(field) for field in FIELDS}
        window_start = now.replace(minute=0)
        label = f"now, {now:%H:%M} local"

    # Total rain over the 24 hours starting at the window (used by the heavy-rain SOP).
    rain_next_24h = sum(
        hourly["precipitation"][i] or 0
        for i, t in enumerate(hour_times)
        if window_start <= t < window_start + timedelta(hours=24)
    )
    values["precipitation_next_24h"] = round(rain_next_24h, 1)
    return {"values": values, "label": label}
