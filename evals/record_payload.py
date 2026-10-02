"""Record a real Open-Meteo payload for deterministic replay (eval case 5b).

    python -m evals.record_payload            # first candidate city with severe conditions right now
    python -m evals.record_payload Bhopal     # try specific cities only
"""
import json
import sys
from datetime import date
from pathlib import Path

from backend import weather
from backend.loader import get_sops

# High-severity SOPs that cover "is it safe to go for a bike ride?"
SEVERE_TARGETS = ["SOP-SIT-01", "SOP-EX-01", "SOP-EX-02"]
# Spread across climates and time zones so at least one is usually severe.
CANDIDATE_CITIES = ["Bhopal", "Mumbai", "Chennai", "Kolkata", "Guwahati", "Dhaka", "Jacobabad",
                    "Riyadh", "Kuwait City", "Phoenix", "Darwin", "Wellington", "Punta Arenas",
                    "Manila", "Hong Kong"]
OUT = Path(__file__).parent / "fixtures" / "severe_recorded.json"


def find_severe(cities=CANDIDATE_CITIES) -> dict | None:
    sops = get_sops()
    for city in cities:
        try:
            loc = weather.geocode(city)
            raw = weather.fetch_forecast(loc["latitude"], loc["longitude"])
        except weather.WeatherUnavailable:
            continue
        values = weather.build_snapshot(raw)["values"]
        hits = [i for i in SEVERE_TARGETS if sops[i].conditions_hold(values)]
        if hits:
            return {"city": city, "location": loc, "forecast": raw, "hits": hits}
    return None


if __name__ == "__main__":
    record = find_severe(sys.argv[1:] or CANDIDATE_CITIES)
    if not record:
        sys.exit("No severe conditions in the candidate cities right now; nothing recorded.")
    record["recorded_on"] = date.today().isoformat()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(record, indent=1), encoding="utf-8")
    print(f"Recorded {record['city']} ({', '.join(record['hits'])}) -> {OUT}")
