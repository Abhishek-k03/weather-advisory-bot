import uuid
from datetime import datetime, timedelta

import pytest

from backend import weather
from backend.graph import run_turn

# A calm, unremarkable day. Tests override only the fields they care about.
CALM = {
    "temperature_2m": 26.4,
    "apparent_temperature": 27.1,
    "precipitation": 0.0,
    "precipitation_probability": 10,
    "wind_speed_10m": 11.2,
    "wind_gusts_10m": 19.8,
    "uv_index": 4.2,
    "pressure_msl": 1012.3,
    "weather_code": 1,
}


def make_payload(**overrides) -> dict:
    """Open-Meteo-shaped forecast with the same values in every hour."""
    values = {**CALM, **overrides}
    start = datetime(2026, 9, 4)
    times = [(start + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(72)]
    return {"current": {"time": "2026-09-04T09:00", **values},
            "hourly": {"time": times, **{f: [v] * 72 for f, v in values.items()}}}


@pytest.fixture
def fake_forecast(monkeypatch):
    """Replace only the forecast HTTP call. Geocoding, snapshot building,
    SOP matching and the LLM all still run for real."""
    def use(**overrides):
        payload = make_payload(**overrides)
        monkeypatch.setattr(weather, "fetch_forecast", lambda lat, lon: payload)
        return payload
    return use


@pytest.fixture
def ask():
    def _ask(message: str, session_id: str | None = None) -> dict:
        state = run_turn(session_id or str(uuid.uuid4()), message)
        print(f"\nQ: {message}\nPATH: {state['path']}  SOPS: {state.get('sop_ids')}\nA: {state['reply']}")
        return state
    return _ask
