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

UNITS = {
    "temperature_2m": "°C",
    "apparent_temperature": "°C",
    "precipitation": "mm",
    "precipitation_probability": "%",
    "wind_speed_10m": "km/h",
    "wind_gusts_10m": "km/h",
    "uv_index": "",
    "pressure_msl": "hPa",
    "weather_code": "(WMO)",
    "precipitation_next_24h": "mm",
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


def _worst(values):
    present = [v for v in values if v is not None]
    return max(present) if present else None


def build_snapshot(data: dict, time_window: str = "now") -> dict:
    """Reduce a raw forecast to one dict of numbers for the asked-about window.

    "now" uses the current block; other windows take the worst (max) hourly
    value of each field, so a threshold crossed at any hour in the window counts.
    """
    hourly = data["hourly"]
    times = [datetime.fromisoformat(t) for t in hourly["time"]]
    now = datetime.fromisoformat(data["current"]["time"])

    if time_window in WINDOWS:
        day, first, last = WINDOWS[time_window]
        date = (now + timedelta(days=day)).date()
        idx = [i for i, t in enumerate(times) if t.date() == date and first <= t.hour <= last]
        if not idx:
            raise WeatherUnavailable(f"no hourly forecast for {time_window}")
        values = {f: _worst(hourly[f][i] for i in idx) for f in FIELDS}
        start = times[idx[0]]
        label = f"{time_window}, {times[idx[0]]:%H}:00-{times[idx[-1]]:%H}:59 local, worst hour"
    else:
        values = {f: data["current"].get(f) for f in FIELDS}
        start = now.replace(minute=0)
        label = f"now, {now:%H:%M} local"

    next_24h = [hourly["precipitation"][i] or 0 for i, t in enumerate(times)
                if start <= t < start + timedelta(hours=24)]
    values["precipitation_next_24h"] = round(sum(next_24h), 1)
    return {"values": values, "label": label}


def get_weather(city: str, time_window: str = "now") -> dict:
    loc = geocode(city)
    snapshot = build_snapshot(fetch_forecast(loc["latitude"], loc["longitude"]), time_window)
    return {"location": loc, **snapshot}
