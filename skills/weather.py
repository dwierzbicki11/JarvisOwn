import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path.home() / "jarvis" / ".env")

CITY = os.getenv("WEATHER_CITY", "Kraków")
LAT = float(os.getenv("WEATHER_LAT", "50.0647"))
LON = float(os.getenv("WEATHER_LON", "19.9450"))

_CACHE = {}
CACHE_SECONDS = 180

WEATHER_CODES = {
    0: "bezchmurnie",
    1: "przeważnie pogodnie",
    2: "częściowe zachmurzenie",
    3: "pochmurno",
    45: "mgła",
    48: "mgła osadzająca szadź",
    51: "lekka mżawka",
    53: "mżawka",
    55: "silna mżawka",
    61: "lekki deszcz",
    63: "deszcz",
    65: "silny deszcz",
    71: "lekki śnieg",
    73: "śnieg",
    75: "silny śnieg",
    80: "przelotny deszcz",
    81: "przelotne opady",
    82: "silne przelotne opady",
    95: "burza",
    96: "burza z gradem",
    99: "silna burza z gradem",
}


def _fetch():
    old = _CACHE.get("forecast")

    if old and time.monotonic() - old["time"] < CACHE_SECONDS:
        return old["data"]

    response = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": LAT,
            "longitude": LON,
            "current": "temperature_2m,apparent_temperature,weather_code",
            "daily": (
                "weather_code,temperature_2m_max,temperature_2m_min,"
                "precipitation_probability_max"
            ),
            "timezone": "Europe/Warsaw",
            "forecast_days": 3,
        },
        timeout=8,
    )
    response.raise_for_status()
    data = response.json()
    _CACHE["forecast"] = {"time": time.monotonic(), "data": data}
    return data


def get_weather(tomorrow=False):
    try:
        data = _fetch()
    except Exception as exc:
        return f"Nie mogę teraz pobrać pogody. {exc}"

    if not tomorrow:
        current = data["current"]
        desc = WEATHER_CODES.get(current["weather_code"], "brak opisu")
        return (
            f"W {CITY} jest teraz około "
            f"{round(current['temperature_2m'])} stopni. "
            f"Odczuwalna temperatura to "
            f"{round(current['apparent_temperature'])} stopni. "
            f"{desc.capitalize()}."
        )

    daily = data["daily"]
    index = 1 if len(daily["time"]) > 1 else 0
    desc = WEATHER_CODES.get(daily["weather_code"][index], "brak opisu")

    city_phrase = "Krakowie" if CITY.lower() == "kraków" else CITY

    return (
        f"Jutro w {city_phrase} od "
        f"{round(daily['temperature_2m_min'][index])} do "
        f"{round(daily['temperature_2m_max'][index])} stopni. "
        f"{desc.capitalize()}. "
        f"Maksymalne prawdopodobieństwo opadów wynosi "
        f"{round(daily['precipitation_probability_max'][index])} procent."
    )
