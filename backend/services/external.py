"""Keyless free-API integrations (from the public-apis catalog).

- Open-Meteo  → today's weather for the daily header + morning brief
- Nager.Date  → public holidays for the calendar view
- ZenQuotes   → a daily quote for the brief card

Every call is best-effort with a short timeout and an in-process cache;
the app must never block or break because an external API is down.
"""
from datetime import date

import httpx

from ..config import settings

_cache: dict[str, object] = {}

# WMO weather codes → (emoji, label)
_WMO = {
    0: ("☀️", "Clear"), 1: ("🌤️", "Mostly clear"), 2: ("⛅", "Partly cloudy"),
    3: ("☁️", "Overcast"), 45: ("🌫️", "Fog"), 48: ("🌫️", "Rime fog"),
    51: ("🌦️", "Light drizzle"), 53: ("🌦️", "Drizzle"), 55: ("🌧️", "Heavy drizzle"),
    61: ("🌧️", "Light rain"), 63: ("🌧️", "Rain"), 65: ("🌧️", "Heavy rain"),
    71: ("🌨️", "Light snow"), 73: ("🌨️", "Snow"), 75: ("❄️", "Heavy snow"),
    80: ("🌦️", "Showers"), 81: ("🌧️", "Showers"), 82: ("⛈️", "Violent showers"),
    95: ("⛈️", "Thunderstorm"), 96: ("⛈️", "Thunderstorm + hail"), 99: ("⛈️", "Thunderstorm + hail"),
}


async def todays_weather() -> dict | None:
    """{'emoji','label','temp_max','temp_min'} or None."""
    if not settings.LATITUDE or not settings.LONGITUDE:
        return None
    key = f"weather:{date.today().isoformat()}"
    if key in _cache:
        return _cache[key]
    try:
        async with httpx.AsyncClient(timeout=6) as client:
            r = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": settings.LATITUDE,
                    "longitude": settings.LONGITUDE,
                    "daily": "weather_code,temperature_2m_max,temperature_2m_min",
                    "timezone": "auto",
                    "forecast_days": 1,
                },
            )
            r.raise_for_status()
            d = r.json()["daily"]
            emoji, label = _WMO.get(d["weather_code"][0], ("🌡️", "Weather"))
            out = {
                "emoji": emoji,
                "label": label,
                "temp_max": round(d["temperature_2m_max"][0]),
                "temp_min": round(d["temperature_2m_min"][0]),
            }
            _cache[key] = out
            return out
    except Exception:
        return None


async def holidays(year: int) -> dict[str, str]:
    """{iso_date: holiday_name} for the configured country."""
    key = f"holidays:{settings.COUNTRY_CODE}:{year}"
    if key in _cache:
        return _cache[key]
    try:
        async with httpx.AsyncClient(timeout=6) as client:
            r = await client.get(
                f"https://date.nager.at/api/v3/PublicHolidays/{year}/{settings.COUNTRY_CODE}"
            )
            r.raise_for_status()
            out = {h["date"]: h["localName"] for h in r.json()}
            _cache[key] = out
            return out
    except Exception:
        return {}


async def daily_quote() -> dict | None:
    """{'text','author'} or None."""
    key = f"quote:{date.today().isoformat()}"
    if key in _cache:
        return _cache[key]
    try:
        async with httpx.AsyncClient(timeout=6) as client:
            r = await client.get("https://zenquotes.io/api/today")
            r.raise_for_status()
            q = r.json()[0]
            out = {"text": q["q"], "author": q["a"]}
            _cache[key] = out
            return out
    except Exception:
        return None
