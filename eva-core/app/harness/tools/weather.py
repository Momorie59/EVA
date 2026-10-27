from typing import Any

import httpx

from ..permissions import Permission
from .base import Tool

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Table de codes WMO utilisée par Open-Meteo — voir https://open-meteo.com/en/docs
WMO_DESCRIPTIONS = {
    0: "ciel dégagé",
    1: "plutôt dégagé",
    2: "partiellement nuageux",
    3: "couvert",
    45: "brouillard",
    48: "brouillard givrant",
    51: "bruine légère",
    53: "bruine",
    55: "bruine dense",
    56: "bruine verglaçante légère",
    57: "bruine verglaçante",
    61: "pluie légère",
    63: "pluie",
    65: "forte pluie",
    66: "pluie verglaçante légère",
    67: "pluie verglaçante",
    71: "neige légère",
    73: "neige",
    75: "forte neige",
    77: "grains de neige",
    80: "averses légères",
    81: "averses",
    82: "fortes averses",
    85: "averses de neige légères",
    86: "fortes averses de neige",
    95: "orage",
    96: "orage avec grêle légère",
    99: "orage avec forte grêle",
}


import time as _time

_GEO: dict[str, dict] = {}            # nom de ville -> lieu (ne change pas : gardé tant qu'EVA tourne)
_FORECAST: dict[tuple, tuple[float, dict]] = {}
FORECAST_TTL = 600                    # 10 min : la météo ne bouge pas plus vite
_client: httpx.AsyncClient | None = None


def _http() -> httpx.AsyncClient:
    """Un client partagé garde la connexion ouverte : plus de poignée de main TLS à chaque demande."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(6.0, connect=3.0), limits=httpx.Limits(max_keepalive_connections=4))
    return _client


def _describe(code: int) -> str:
    return WMO_DESCRIPTIONS.get(code, f"code météo {code}")


class WeatherTool(Tool):
    name = "weather_get"
    description = (
        "Donne la météo actuelle et les prochains jours pour une ville. "
        "Utilise le nom de la ville tel que dit par l'utilisateur (ex: "
        "'Paris', 'Palerme', 'Sète')."
    )
    parameters = {
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "Nom de la ville"},
            "days": {
                "type": "integer",
                "description": "Nombre de jours de prévisions à inclure (1 à 7, défaut 3)",
            },
        },
        "required": ["city"],
    }
    permission = Permission.AUTO

    async def execute(self, city: str, days: int = 3, **_: Any) -> dict:
        days = max(1, min(days, 7))
        key = " ".join(city.lower().split())
        hit = _FORECAST.get((key, days))
        if hit and _time.monotonic() - hit[0] < FORECAST_TTL:
            return hit[1]
        client = _http()
        place = _GEO.get(key)
        if not place:
            try:
                geo_resp = await client.get(GEOCODE_URL, params={"name": city, "count": 1, "language": "fr"})
                geo_resp.raise_for_status()
                geo_data = geo_resp.json()
            except httpx.HTTPError as exc:
                return {"error": f"Service de géocodage injoignable : {exc}"}
            results = geo_data.get("results") or []
            if not results:
                return {"error": f"Ville introuvable : {city}"}
            place = _GEO[key] = results[0]
        lat, lon = place["latitude"], place["longitude"]
        resolved_name = place.get("name", city)
        country = place.get("country", "")

        try:
            weather_resp = await client.get(
                FORECAST_URL,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current_weather": "true",
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weathercode",
                    "timezone": "auto",
                    "forecast_days": days,
                },
            )
            weather_resp.raise_for_status()
            weather_data = weather_resp.json()
        except httpx.HTTPError as exc:
            return {"error": f"Service météo injoignable : {exc}"}

        current = weather_data.get("current_weather", {})
        daily = weather_data.get("daily", {})

        forecast = []
        for i, day in enumerate(daily.get("time", [])):
            forecast.append(
                {
                    "date": day,
                    "temp_min": daily.get("temperature_2m_min", [None] * len(daily.get("time", [])))[i],
                    "temp_max": daily.get("temperature_2m_max", [None] * len(daily.get("time", [])))[i],
                    "precipitation_probability_max": daily.get(
                        "precipitation_probability_max", [None] * len(daily.get("time", []))
                    )[i],
                    "condition": _describe(daily.get("weathercode", [None] * len(daily.get("time", [])))[i]),
                }
            )

        out = {
            "city": resolved_name,
            "country": country,
            "current": {
                "temperature_c": current.get("temperature"),
                "windspeed_kmh": current.get("windspeed"),
                "condition": _describe(current.get("weathercode", -1)),
                "time": current.get("time"),
            },
            "forecast": forecast,
        }
        _FORECAST[(key, days)] = (_time.monotonic(), out)
        return out
