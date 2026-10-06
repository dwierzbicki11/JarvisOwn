import csv
import io
import os
import re
import time
import unicodedata
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

load_dotenv(Path.home() / "jarvis" / ".env")

TIMEZONE = ZoneInfo("Europe/Warsaw")
BASE_URL = "https://gtfs.ztp.krakow.pl"
CACHE_DIR = Path.home() / "jarvis" / "cache"

HOME_STOP = os.getenv(
    "JARVIS_HOME_STOP",
    "Garlica Duchowna Kapliczka",
).strip()

PK_STOP = os.getenv(
    "JARVIS_PK_STOP",
    "AKF / PK",
).strip()

HOME_WALK_MINUTES = int(os.getenv("JARVIS_HOME_WALK_MINUTES", "5"))
PK_WALK_MINUTES = int(os.getenv("JARVIS_PK_WALK_MINUTES", "8"))
CLASS_BUFFER_MINUTES = int(os.getenv("JARVIS_CLASS_BUFFER_MINUTES", "10"))
TRANSFER_MINUTES = int(os.getenv("JARVIS_TRANSFER_MINUTES", "3"))

FEEDS = {
    "A": "GTFS_KRK_A.zip",
    "M": "GTFS_KRK_M.zip",
    "T": "GTFS_KRK_T.zip",
}

CACHE_SECONDS = 6 * 60 * 60
_DAY_CACHE = {}


def normalize(text):
    text = unicodedata.normalize("NFKD", text.lower().strip())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).strip()


def clean_stop_name(name):
    if not name:
        return ""
    return re.sub(r"\s+\d{2}$", "", re.sub(r"\s+", " ", name).strip())


HOUR_WORDS = {
    0: "północy", 1: "pierwszej", 2: "drugiej", 3: "trzeciej",
    4: "czwartej", 5: "piątej", 6: "szóstej", 7: "siódmej",
    8: "ósmej", 9: "dziewiątej", 10: "dziesiątej",
    11: "jedenastej", 12: "dwunastej", 13: "trzynastej",
    14: "czternastej", 15: "piętnastej", 16: "szesnastej",
    17: "siedemnastej", 18: "osiemnastej", 19: "dziewiętnastej",
    20: "dwudziestej", 21: "dwudziestej pierwszej",
    22: "dwudziestej drugiej", 23: "dwudziestej trzeciej",
}

NUMBER_0_19 = {
    0: "zero", 1: "jeden", 2: "dwa", 3: "trzy", 4: "cztery",
    5: "pięć", 6: "sześć", 7: "siedem", 8: "osiem",
    9: "dziewięć", 10: "dziesięć", 11: "jedenaście",
    12: "dwanaście", 13: "trzynaście", 14: "czternaście",
    15: "piętnaście", 16: "szesnaście", 17: "siedemnaście",
    18: "osiemnaście", 19: "dziewiętnaście",
}

TENS = {
    20: "dwadzieścia",
    30: "trzydzieści",
    40: "czterdzieści",
    50: "pięćdziesiąt",
}


def number_words(number):
    if number <= 19:
        return NUMBER_0_19[number]

    tens = number // 10 * 10
    rest = number % 10

    if rest == 0:
        return TENS[tens]

    return TENS[tens] + " " + NUMBER_0_19[rest]


def speak_time(dt):
    hour = HOUR_WORDS[dt.hour]

    if dt.minute == 0:
        return hour

    if dt.minute < 10:
        minute = "zero " + NUMBER_0_19[dt.minute]
    else:
        minute = number_words(dt.minute)

    return f"{hour} {minute}"


def gtfs_seconds(value):
    try:
        h, m, s = [int(x) for x in value.split(":")]
        return h * 3600 + m * 60 + s
    except Exception:
        return None


def seconds_to_datetime(service_date, seconds):
    midnight = datetime(
        service_date.year,
        service_date.month,
        service_date.day,
        tzinfo=TIMEZONE,
    )
    return midnight + timedelta(seconds=seconds)


def read_csv(archive, filename, optional=False):
    try:
        raw = archive.open(filename)
    except KeyError:
        if optional:
            return []
        raise

    with raw:
        text = io.TextIOWrapper(raw, encoding="utf-8-sig")
        return list(csv.DictReader(text))


def gtfs_path(code):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / FEEDS[code]


def download_feed(code):
    path = gtfs_path(code)

    if path.exists():
        age = time.time() - path.stat().st_mtime
        if age < CACHE_SECONDS:
            return path

    print(f"🚌 Aktualizuję GTFS {code}...", flush=True)

    response = requests.get(
        f"{BASE_URL}/{FEEDS[code]}",
        timeout=30,
    )
    response.raise_for_status()

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(response.content)
    tmp.replace(path)
    return path


def active_services(calendar_rows, exception_rows, target_date):
    active = set()
    date_string = target_date.strftime("%Y%m%d")
    weekday = target_date.strftime("%A").lower()

    for row in calendar_rows:
        if (
            row.get("start_date", "") <= date_string <= row.get("end_date", "")
            and row.get(weekday, "0") == "1"
        ):
            active.add(row["service_id"])

    for row in exception_rows:
        if row.get("date") != date_string:
            continue

        service_id = row.get("service_id")
        kind = row.get("exception_type")

        if kind == "1":
            active.add(service_id)
        elif kind == "2":
            active.discard(service_id)

    return active


def load_day(target_date):
    """
    Najdroższa operacja. Dane jednego dnia są trzymane w RAM przez 6h,
    więc kolejne pytania nie parsują ponownie wszystkich stop_times.txt.
    """
    key = target_date.isoformat()
    cached = _DAY_CACHE.get(key)

    if cached and time.monotonic() - cached["time"] < CACHE_SECONDS:
        return cached["data"]

    trips = {}
    routes = {}
    stops = {}
    stop_times = defaultdict(list)

    for code in FEEDS:
        try:
            path = download_feed(code)

            with zipfile.ZipFile(path, "r") as archive:
                stop_rows = read_csv(archive, "stops.txt")
                route_rows = read_csv(archive, "routes.txt")
                trip_rows = read_csv(archive, "trips.txt")
                time_rows = read_csv(archive, "stop_times.txt")
                calendar_rows = read_csv(archive, "calendar.txt", optional=True)
                exception_rows = read_csv(
                    archive,
                    "calendar_dates.txt",
                    optional=True,
                )

            services = active_services(
                calendar_rows,
                exception_rows,
                target_date,
            )
            calendar_known = bool(calendar_rows or exception_rows)

            raw_stops = {
                row.get("stop_id", ""): {
                    "name": row.get("stop_name", "").strip(),
                    "parent": row.get("parent_station", "").strip(),
                }
                for row in stop_rows
            }

            for raw_id, stop in raw_stops.items():
                parent = stop["parent"]
                name = stop["name"]

                if parent and parent in raw_stops:
                    name = raw_stops[parent]["name"] or name

                name = clean_stop_name(name)

                stops[f"{code}:{raw_id}"] = {
                    "name": name,
                    "normalized": normalize(name),
                }

            for row in route_rows:
                raw_id = row.get("route_id", "")
                routes[f"{code}:{raw_id}"] = (
                    row.get("route_short_name")
                    or row.get("route_long_name")
                    or raw_id
                )

            valid_trip_ids = set()

            for row in trip_rows:
                if (
                    calendar_known
                    and row.get("service_id") not in services
                ):
                    continue

                raw_trip_id = row.get("trip_id", "")
                trip_id = f"{code}:{raw_trip_id}"

                trips[trip_id] = {
                    "route_id": f"{code}:{row.get('route_id', '')}",
                    "headsign": clean_stop_name(
                        row.get("trip_headsign", "").strip()
                    ),
                }

                valid_trip_ids.add(raw_trip_id)

            for row in time_rows:
                raw_trip_id = row.get("trip_id", "")

                if raw_trip_id not in valid_trip_ids:
                    continue

                departure = gtfs_seconds(row.get("departure_time", ""))
                arrival = gtfs_seconds(row.get("arrival_time", ""))

                if departure is None:
                    departure = arrival

                if arrival is None:
                    arrival = departure

                if departure is None or arrival is None:
                    continue

                try:
                    sequence = int(row.get("stop_sequence", "0"))
                except Exception:
                    sequence = 0

                stop_times[f"{code}:{raw_trip_id}"].append(
                    {
                        "stop_id": f"{code}:{row.get('stop_id', '')}",
                        "arrival": arrival,
                        "departure": departure,
                        "sequence": sequence,
                    }
                )

        except Exception as exc:
            print(f"[ROUTE GTFS {code}] {exc}", flush=True)

    for trip_id in stop_times:
        stop_times[trip_id].sort(key=lambda item: item["sequence"])

    departures_by_stop = defaultdict(list)

    for trip_id, events in stop_times.items():
        for position, event in enumerate(events):
            stop = stops.get(event["stop_id"])

            if not stop:
                continue

            departures_by_stop[stop["normalized"]].append(
                (event["departure"], trip_id, position)
            )

    for stop_name in departures_by_stop:
        departures_by_stop[stop_name].sort(key=lambda item: item[0])

    data = {
        "trips": trips,
        "routes": routes,
        "stops": stops,
        "stop_times": stop_times,
        "departures_by_stop": departures_by_stop,
    }

    _DAY_CACHE.clear()
    _DAY_CACHE[key] = {
        "time": time.monotonic(),
        "data": data,
    }

    return data


def matching_stop_ids(data, requested_name):
    target = normalize(clean_stop_name(requested_name))
    exact = set()
    partial = set()

    for stop_id, stop in data["stops"].items():
        name = stop["normalized"]

        if name == target:
            exact.add(stop_id)
        elif target in name or name in target:
            partial.add(stop_id)

    return exact or partial


def find_journey(
    target_date,
    origin_name,
    destination_name,
    latest_arrival,
):
    data = load_day(target_date)

    origin_ids = matching_stop_ids(data, origin_name)
    destination_ids = matching_stop_ids(data, destination_name)

    if not origin_ids:
        return {"error": f"Nie znalazłem przystanku {origin_name}."}

    if not destination_ids:
        return {"error": f"Nie znalazłem przystanku {destination_name}."}

    midnight = datetime(
        target_date.year,
        target_date.month,
        target_date.day,
        tzinfo=TIMEZONE,
    )
    latest_seconds = int((latest_arrival - midnight).total_seconds())

    candidates = []
    first_trip_positions = []

    for trip_id, events in data["stop_times"].items():
        for pos, event in enumerate(events):
            if event["stop_id"] in origin_ids:
                first_trip_positions.append((trip_id, pos))

    for trip1_id, origin_pos in first_trip_positions:
        events1 = data["stop_times"][trip1_id]
        departure1 = events1[origin_pos]["departure"]

        if departure1 > latest_seconds:
            continue

        # Bezpośrednie połączenie.
        for destination_pos in range(origin_pos + 1, len(events1)):
            event = events1[destination_pos]

            if event["stop_id"] not in destination_ids:
                continue

            if event["arrival"] <= latest_seconds:
                candidates.append(
                    {
                        "departure": departure1,
                        "arrival": event["arrival"],
                        "legs": [
                            {
                                "trip_id": trip1_id,
                                "from_pos": origin_pos,
                                "to_pos": destination_pos,
                            }
                        ],
                    }
                )

            break

        # Jedna przesiadka.
        for transfer_pos in range(origin_pos + 1, len(events1)):
            transfer_event = events1[transfer_pos]
            transfer_stop = data["stops"].get(transfer_event["stop_id"])

            if not transfer_stop:
                continue

            earliest = (
                transfer_event["arrival"]
                + TRANSFER_MINUTES * 60
            )

            departures = data["departures_by_stop"].get(
                transfer_stop["normalized"],
                [],
            )

            checked = 0

            for departure2, trip2_id, transfer2_pos in departures:
                if departure2 < earliest:
                    continue

                if departure2 > latest_seconds:
                    break

                if trip2_id == trip1_id:
                    continue

                checked += 1

                if checked > 12:
                    break

                events2 = data["stop_times"][trip2_id]

                for destination2_pos in range(
                    transfer2_pos + 1,
                    len(events2),
                ):
                    event2 = events2[destination2_pos]

                    if event2["stop_id"] not in destination_ids:
                        continue

                    if event2["arrival"] <= latest_seconds:
                        candidates.append(
                            {
                                "departure": departure1,
                                "arrival": event2["arrival"],
                                "legs": [
                                    {
                                        "trip_id": trip1_id,
                                        "from_pos": origin_pos,
                                        "to_pos": transfer_pos,
                                    },
                                    {
                                        "trip_id": trip2_id,
                                        "from_pos": transfer2_pos,
                                        "to_pos": destination2_pos,
                                    },
                                ],
                            }
                        )

                    break

    if not candidates:
        return {
            "error": (
                "Nie znalazłem połączenia spełniającego "
                "wymagany czas dojazdu."
            )
        }

    candidates.sort(
        key=lambda item: (
            item["departure"],
            -len(item["legs"]),
        ),
        reverse=True,
    )

    journey = candidates[0]
    pretty = []

    for leg in journey["legs"]:
        events = data["stop_times"][leg["trip_id"]]
        start = events[leg["from_pos"]]
        end = events[leg["to_pos"]]
        trip = data["trips"].get(leg["trip_id"], {})

        pretty.append(
            {
                "route": data["routes"].get(trip.get("route_id", ""), "?"),
                "headsign": trip.get("headsign", ""),
                "from": data["stops"].get(
                    start["stop_id"],
                    {"name": "przystanek"},
                )["name"],
                "to": data["stops"].get(
                    end["stop_id"],
                    {"name": "przystanek"},
                )["name"],
                "departure": seconds_to_datetime(
                    target_date,
                    start["departure"],
                ),
                "arrival": seconds_to_datetime(
                    target_date,
                    end["arrival"],
                ),
            }
        )

    return {
        "departure": seconds_to_datetime(
            target_date,
            journey["departure"],
        ),
        "arrival": seconds_to_datetime(
            target_date,
            journey["arrival"],
        ),
        "legs": pretty,
    }


def format_journey(journey, class_time=None):
    if "error" in journey:
        return journey["error"]

    leave_home = journey["departure"] - timedelta(
        minutes=HOME_WALK_MINUTES
    )

    parts = [
        "Powinieneś wyjść z domu około "
        + speak_time(leave_home)
        + "."
    ]

    for index, leg in enumerate(journey["legs"]):
        prefix = (
            f"Z przystanku {leg['from']} "
            if index == 0
            else f"Następnie z przystanku {leg['from']} "
        )

        text = prefix + f"jedź linią {leg['route']} "

        if leg["headsign"]:
            text += f"w kierunku {leg['headsign']}, "

        text += (
            "odjazd o "
            + speak_time(leg["departure"])
            + ", do przystanku "
            + leg["to"]
            + "."
        )

        parts.append(text)

    parts.append(
        f"Na przystanku {PK_STOP} powinieneś być około "
        + speak_time(journey["arrival"])
        + "."
    )

    if class_time:
        parts.append(
            "Pierwsze zajęcia zaczynają się o "
            + speak_time(class_time)
            + "."
        )

    return " ".join(parts)
