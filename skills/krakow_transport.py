import csv
import io
import os
import re
import time
import unicodedata
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv
from google.transit import gtfs_realtime_pb2

load_dotenv(Path.home() / "jarvis" / ".env")

BASE_URL = "https://gtfs.ztp.krakow.pl"
CACHE_DIR = Path.home() / "jarvis" / "cache"
TIMEZONE = ZoneInfo("Europe/Warsaw")

FEEDS = {
    "A": {
        "static": "GTFS_KRK_A.zip",
        "trip": "TripUpdates_A.pb",
        "alerts": "ServiceAlerts_A.pb",
    },
    "M": {
        "static": "GTFS_KRK_M.zip",
        "trip": "TripUpdates_M.pb",
        "alerts": "ServiceAlerts_M.pb",
    },
    "T": {
        "static": "GTFS_KRK_T.zip",
        "trip": "TripUpdates_T.pb",
        "alerts": "ServiceAlerts_T.pb",
    },
}

STATIC_TTL = 6 * 60 * 60
_STATIC_CACHE = {}


def _normalize(text):
    text = unicodedata.normalize("NFKD", text.lower().strip())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"\s+\d{2}$", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _static_path(code):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / FEEDS[code]["static"]


def _download_static(code):
    path = _static_path(code)

    if path.exists() and time.time() - path.stat().st_mtime < STATIC_TTL:
        return path

    print(f"🚌 Aktualizuję GTFS {code}...", flush=True)
    response = requests.get(
        f"{BASE_URL}/{FEEDS[code]['static']}",
        timeout=20,
    )
    response.raise_for_status()

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(response.content)
    tmp.replace(path)
    return path


def _rows(archive, name):
    with archive.open(name) as raw:
        with io.TextIOWrapper(raw, encoding="utf-8-sig") as text:
            return list(csv.DictReader(text))


def _load_static(code):
    cached = _STATIC_CACHE.get(code)
    path = _download_static(code)
    stamp = path.stat().st_mtime

    if cached and cached["stamp"] == stamp:
        return cached["data"]

    with zipfile.ZipFile(path, "r") as archive:
        stops_rows = _rows(archive, "stops.txt")
        trips_rows = _rows(archive, "trips.txt")
        routes_rows = _rows(archive, "routes.txt")

    raw_stops = {
        row["stop_id"]: {
            "name": row.get("stop_name", "").strip(),
            "parent": row.get("parent_station", "").strip(),
        }
        for row in stops_rows
    }

    stops = {}

    for stop_id, stop in raw_stops.items():
        name = stop["name"]
        parent = stop["parent"]

        if parent and parent in raw_stops:
            name = raw_stops[parent]["name"] or name

        stops[stop_id] = {
            "name": re.sub(r"\s+\d{2}$", "", name).strip(),
            "norm": _normalize(name),
        }

    routes = {
        row["route_id"]: (
            row.get("route_short_name")
            or row.get("route_long_name")
            or row["route_id"]
        )
        for row in routes_rows
    }

    trips = {
        row["trip_id"]: {
            "route": routes.get(row.get("route_id", ""), "?"),
            "headsign": re.sub(
                r"\s+\d{2}$",
                "",
                row.get("trip_headsign", "").strip(),
            ),
        }
        for row in trips_rows
    }

    data = {"stops": stops, "trips": trips}
    _STATIC_CACHE[code] = {"stamp": stamp, "data": data}
    return data


def _matching_stop_ids(stops, requested):
    target = _normalize(requested)

    exact = {
        stop_id
        for stop_id, stop in stops.items()
        if stop["norm"] == target
    }

    if exact:
        return exact

    return {
        stop_id
        for stop_id, stop in stops.items()
        if target in stop["norm"] or stop["norm"] in target
    }


def next_departures(stop_name, limit=5):
    now_ts = int(datetime.now(TIMEZONE).timestamp())
    found = []

    for code in FEEDS:
        try:
            static = _load_static(code)
            stop_ids = _matching_stop_ids(static["stops"], stop_name)

            if not stop_ids:
                continue

            response = requests.get(
                f"{BASE_URL}/{FEEDS[code]['trip']}",
                timeout=8,
            )
            response.raise_for_status()

            feed = gtfs_realtime_pb2.FeedMessage()
            feed.ParseFromString(response.content)

            for entity in feed.entity:
                if not entity.HasField("trip_update"):
                    continue

                update = entity.trip_update
                trip_id = update.trip.trip_id
                trip = static["trips"].get(
                    trip_id,
                    {"route": "?", "headsign": ""},
                )

                for stu in update.stop_time_update:
                    if stu.stop_id not in stop_ids:
                        continue

                    departure = 0

                    if stu.HasField("departure") and stu.departure.time:
                        departure = stu.departure.time
                    elif stu.HasField("arrival") and stu.arrival.time:
                        departure = stu.arrival.time

                    if departure <= now_ts - 60:
                        continue

                    found.append(
                        {
                            "timestamp": departure,
                            "route": trip["route"],
                            "headsign": trip["headsign"],
                        }
                    )

        except Exception as exc:
            print(f"[GTFS RT {code}] {exc}", flush=True)

    if not found:
        return (
            f"Nie widzę teraz najbliższych odjazdów "
            f"z {stop_name} w danych czasu rzeczywistego."
        )

    found.sort(key=lambda item: item["timestamp"])

    parts = []

    for item in found[:limit]:
        dt = datetime.fromtimestamp(item["timestamp"], TIMEZONE)
        minutes = max(0, round((item["timestamp"] - now_ts) / 60))
        text = f"linia {item['route']}"

        if item["headsign"]:
            text += f" w kierunku {item['headsign']}"

        text += (
            f", za około {minutes} minut, "
            f"o {dt.strftime('%H:%M')}"
        )

        parts.append(text)

    return (
        f"Najbliższe odjazdy z {stop_name}: "
        + ". ".join(parts)
        + "."
    )


def _translation_text(translated):
    if not translated.translation:
        return ""

    for item in translated.translation:
        if item.language in ("pl", "pl-PL"):
            return item.text.strip()

    return translated.translation[0].text.strip()


def transit_alerts(limit=2):
    generic = {
        "ogólny tekst specjalny",
        "ogolny tekst specjalny",
        "informacja",
        "komunikat",
    }
    texts = []

    for code in FEEDS:
        try:
            response = requests.get(
                f"{BASE_URL}/{FEEDS[code]['alerts']}",
                timeout=8,
            )
            response.raise_for_status()

            feed = gtfs_realtime_pb2.FeedMessage()
            feed.ParseFromString(response.content)

            for entity in feed.entity:
                if not entity.HasField("alert"):
                    continue

                alert = entity.alert
                text = ""

                if alert.HasField("header_text"):
                    text = _translation_text(alert.header_text)

                if not text and alert.HasField("description_text"):
                    text = _translation_text(alert.description_text)

                norm = _normalize(text)

                if not text or norm in generic or text in texts:
                    continue

                texts.append(text)

        except Exception as exc:
            print(f"[GTFS ALERT {code}] {exc}", flush=True)

    if not texts:
        return (
            "Nie widzę obecnie komunikatów o utrudnieniach "
            "w danych ZTP."
        )

    return "Utrudnienia: " + " ".join(texts[:limit])
